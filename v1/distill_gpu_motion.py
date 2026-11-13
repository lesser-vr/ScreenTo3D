"""Pinned Small engines through the actual GPU postprocessor, public media only."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import cv2
import numpy as np

from compare_small_aspect import digest
from distill_small_experiment import ROOT

PLANS = {
    'da2': 'b0b6b745e9c3bd00317248bed833eee0d689ceeaaa11bb08a79d73d6531855c8',
    'distill': '3b8e2a94ba6553deb529d9e4c82eccd60418adbd37c27164071e9e821f13e810',
}


def local_engine(name):
    """Use the production ownership methods, with an isolated pinned initializer."""
    if name not in PLANS:
        raise ValueError('Unreviewed experimental model')
    path = ROOT/'out/p1-distill-small-20260909'/f'{name}-small-fp32.plan'
    if digest(path) != PLANS[name]:
        raise ValueError('Local engine integrity mismatch')
    from screento3d_app.trt_backend import DepthEngine, _cuda, cudart, trt
    if trt.__version__ != '11.2.1.2':
        raise ValueError('Wrong TensorRT runtime')

    class PinnedEngine(DepthEngine):
        def _initialize(self, progress):
            self.logger = trt.Logger(trt.Logger.WARNING)
            self.runtime = trt.Runtime(self.logger)
            self.engine = self.runtime.deserialize_cuda_engine(path.read_bytes())
            if self.engine is None or self.engine.num_io_tensors != 2:
                raise ValueError('Invalid fixed Small engine')
            self.context = self.engine.create_execution_context()
            if self.context is None or not self.context.set_input_shape('pixel_values', (1, 3, 518, 518)):
                raise ValueError('Input shape rejected')
            for tensor, expected in [('pixel_values', (1, 3, 518, 518)), ('predicted_depth', (1, 518, 518))]:
                if (tuple(self.context.get_tensor_shape(tensor)) != expected
                        or self.engine.get_tensor_dtype(tensor) != trt.float32):
                    raise ValueError('Invalid Small I/O contract')
            self.input_bytes, self.output_bytes = 1*3*518*518*4, 1*518*518*4
            self.device_input = _cuda(cudart.cudaMalloc(self.input_bytes))
            self.device_output = _cuda(cudart.cudaMalloc(self.output_bytes))
            self.stream = _cuda(cudart.cudaStreamCreate())
            self.output = np.empty((1, 518, 518), np.float32)
            for tensor, pointer in [('pixel_values', self.device_input), ('predicted_depth', self.device_output)]:
                if not self.context.set_tensor_address(tensor, int(pointer)):
                    raise ValueError('Binding failed')
            self._sample_memory(force=True)
    return PinnedEngine()


class Encoder:
    def __init__(self, ffmpeg, path):
        self.path = path
        self.log = path.with_suffix('.log').open('wb')
        try:
            self.process = subprocess.Popen([str(ffmpeg), '-v', 'error', '-nostdin', '-n',
                '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '7680x2160', '-r', '60',
                '-i', 'pipe:0', '-an', '-c:v', 'hevc_nvenc', '-preset', 'p3', '-cq', '20',
                '-pix_fmt', 'yuv420p', '-tag:v', 'hvc1', str(path)],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log)
        except BaseException:
            self.log.close()
            raise

    def write(self, frame):
        if frame.shape != (2160, 7680, 3) or frame.dtype != np.uint8:
            raise ValueError('Invalid SBS encoder frame')
        self.process.stdin.write(np.ascontiguousarray(frame).tobytes())

    def close(self, failed=False):
        try:
            close_error = None
            try:
                self.process.stdin.close()
            except OSError as error:
                close_error = error
            if (failed or close_error is not None) and self.process.poll() is None:
                self.process.terminate()
            try:
                code = self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
                raise RuntimeError('Owned encoder timeout')
            if code != 0 and not failed:
                raise RuntimeError('Encoder failed; see retained log')
            if close_error is not None and not failed:
                raise RuntimeError('Encoder input close failed') from close_error
        finally:
            self.log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=360)
    args = parser.parse_args()
    if not 60 <= args.frames <= 360:
        raise ValueError('Expected 60..360 frames per clip')
    args.output.mkdir(parents=True, exist_ok=False)
    from screento3d_app.desktop_jobs import BUNDLE
    from screento3d_app.resources import configure_resource_root
    configure_resource_root(BUNDLE)
    ffmpeg, ffprobe = BUNDLE/'ffmpeg/ffmpeg.exe', BUNDLE/'ffmpeg/ffprobe.exe'
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise ValueError('Prepared media tools missing')
    from public_test_media import SOURCES
    report = dict(status='incomplete', frames_per_clip=args.frames, models=PLANS, cases=[], videos=[],
        scope='Offline original-4K public frames through production GPU inference/postprocessor '
              'and host SBS readback; recording encoder may contend. No WGC/native presentation '
              'or headset; output 60fps timestamps do not mean processing at 60fps.',
        input=[3840, 2160], per_eye=[3840, 2160], combined=[7680, 2160],
        precision='Both FP32 / TF32 disabled', sources={})
    with os.add_dll_directory('C:/TensorRT/TensorRT-11.2.1.2/bin'):
        from screento3d_app.live_gpu_candidate import LiveGpuCandidate, DLL_SHA256
        from screento3d_app.live_policy import resolve_live
        from screento3d_app.pipeline import preprocess
        report['gpu_dll_sha256'] = DLL_SHA256
        for source_index, (source, expected) in enumerate(SOURCES.items()):
            path = ROOT/'out/public-video-source/uvg-vcm'/f'{source}.mp4'
            if digest(path) != expected:
                raise ValueError('Public source changed')
            report['sources'][source] = expected
            for name in (('da2', 'distill') if source_index % 2 == 0 else ('distill', 'da2')):
                with local_engine(name) as engine, LiveGpuCandidate(3840, 2160, resolve_live('performance'), engine) as gpu:
                    capture = cv2.VideoCapture(str(path))
                    pending = args.output/f'{source}-{name}.partial.mp4'
                    encoder = None
                    succeeded = False
                    try:
                        for index in range(args.frames):
                            ok, bgr = capture.read()
                            if not ok or bgr.shape != (2160, 3840, 3):
                                raise ValueError('Unexpected original 4K source')
                            frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                            if index == 0:
                                # Verify device inference versus the host-input method before timing.
                                host_depth = engine.infer(preprocess(frame))
                                for _ in range(16):
                                    gpu.render(frame, gpu.infer(frame))
                                from screento3d_app.trt_backend import _cuda, cudart
                                device_depth = np.empty_like(host_depth)
                                _cuda(cudart.cudaMemcpy(device_depth.ctypes.data, engine.device_output,
                                    engine.output_bytes, cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost))
                                if not np.allclose(host_depth, device_depth, atol=.001, rtol=.001):
                                    raise RuntimeError('GPU preparation changes depth beyond budget')
                                gpu.reset()
                                encoder = Encoder(ffmpeg, pending)
                            started = time.perf_counter_ns()
                            result = gpu.render(frame, gpu.infer(frame))
                            elapsed = (time.perf_counter_ns()-started)/1e6
                            report['cases'].append(dict(source=source, model=name, frame=index,
                                processing_ms=elapsed, gpu_intervals_ms=gpu.gpu_ms.tolist()))
                            encoder.write(result)
                            if index in (0, args.frames//2, args.frames-1):
                                if not cv2.imwrite(str(args.output/f'{source}-{name}-{index}.jpg'),
                                                   cv2.cvtColor(result, cv2.COLOR_RGB2BGR)):
                                    raise RuntimeError('Review image write failed')
                            if index % 60 == 0:
                                print(source, name, index, round(elapsed, 2), flush=True)
                        succeeded = True
                    finally:
                        capture.release()
                        if encoder is not None:
                            encoder.close(failed=not succeeded)
                # Resources are closed before any final output name is published.
                stream = json.loads(subprocess.check_output([str(ffprobe), '-v', 'error',
                    '-select_streams', 'v:0', '-count_frames', '-show_streams', '-of', 'json', str(pending)],
                    timeout=120))['streams'][0]
                if (stream['width'], stream['height'], int(stream['nb_read_frames'])) != (7680, 2160, args.frames):
                    raise RuntimeError('Encoded geometry/frame count mismatch')
                report['videos'].append(dict(path=str(pending), frames=args.frames, decoded=True))
                (args.output/'partial.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    for video in report['videos']:
        pending = Path(video['path'])
        final = pending.with_name(pending.name.replace('.partial', ''))
        pending.replace(final)
        video.update(path=str(final), sha256=digest(final))
    report['status'] = 'measured'
    report['script_sha256'] = digest(__file__)
    (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('MEASURED', args.output/'report.json', flush=True)


if __name__ == '__main__':
    main()
