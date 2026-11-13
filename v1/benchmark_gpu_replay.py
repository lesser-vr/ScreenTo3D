"""Explicit native-pipeline load probe; excludes WGC/window painting/decoding.

Only public hash-verified frames are cached, bounded to 60 frames. This is not
an alternative product capture source or a live end-to-end FPS measurement.
"""
import os
import threading
import time
from unittest.mock import patch

CACHE_FRAMES = 60


from screento3d_app.environment import required as app_env_required

class PublicGpuReplay:
    def __init__(self, source, cursor, device):
        import cv2
        import torch
        from public_test_media import PublicFrames
        width, height = source['width'], source['height']
        if not 16 <= width <= 4096 or not 16 <= height <= 2160:
            raise ValueError('Invalid GPU replay dimensions')
        self.torch, self.device = torch, device
        self.width, self.height = width, height
        self.thread = threading.get_ident()
        self.frames, self.sequence, self.stream = [], 0, None
        self.closed = False
        try:
            for rgb in PublicFrames(app_env_required('SCREENTO3D_BENCH_REPLAY_SOURCE'), CACHE_FRAMES):
                resized = cv2.resize(rgb,(width,height),interpolation=cv2.INTER_LINEAR)
                bgra = cv2.cvtColor(resized,cv2.COLOR_RGB2BGRA)
                self.frames.append(torch.from_numpy(bgra).to(f'cuda:{device}'))
            torch.cuda.current_stream(device).synchronize()
        except BaseException:
            self.close()
            raise

    def _owner(self):
        if threading.get_ident() != self.thread or self.torch.cuda.current_device() != self.device:
            raise RuntimeError('GPU replay requires its owner thread/device')

    def read(self, stream):
        self._owner()
        if self.closed or stream.device.index != self.device:
            raise RuntimeError('Closed replay or foreign stream')
        self.stream = stream
        stamp = time.perf_counter_ns()
        with self.torch.cuda.stream(stream):
            image = self.frames[self.sequence % len(self.frames)].clone()
        stream.synchronize()  # Owned copy completion, as at the capture boundary.
        self.sequence += 1
        return image, dict(width=self.width,height=self.height,sequence=self.sequence,
            source_ns=stamp,callback_ns=stamp,replaced=0,resizes=0)

    def close(self):
        self._owner()
        if self.stream is not None:
            self.stream.synchronize()
        self.frames.clear()
        self.closed = True

    def __enter__(self): return self

    def __exit__(self, kind, primary, tb):
        try: self.close()
        except Exception as error:
            if primary is None: raise
            primary.add_note(str(error))


def sbs_worker_replay(*args, **kwargs):
    from screento3d_app.live_sbs import sbs_worker
    from screento3d_app import gpu_capture
    if kwargs.get('gpu_capture_snapshot') is not True:
        raise ValueError('GPU replay requires an explicit GPU input session')
    with patch.object(gpu_capture,'GpuCapture',PublicGpuReplay):
        return sbs_worker(*args,**kwargs)
