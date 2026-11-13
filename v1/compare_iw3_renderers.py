"""Pinned iw3 renderer experiment, never imported by the product runtime.

All methods receive the same source RGB and final guided depth. CPU-in/out
latency is comparable; iw3 resident timings exclude transfers and are separate.
"""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

import cv2
import numpy as np
import torch

from screento3d_app.da2_base import binding
from screento3d_app.desktop_jobs import ROOT, BUNDLE
from screento3d_app.live_policy import resolve_live
from screento3d_app.live_projection import LiveProjection
from screento3d_app.pipeline import StereoSynthesizer
from screento3d_app.resources import configure_resource_root
from public_test_media import CORPUS, SOURCES, ATTRIBUTION

REVISION = '0d3d92c8f4396da564c44524b6390ee5c76b9668'
WEIGHTS = {
    'row_flow_v3_sym': ('iw3_row_flow_v3_sym_20250628.pth', 'b61518f9c83e1f0c19d8a8844dbe5304e5f47bfb65928d5bb74256c1640186a0'),
    'row_flow_v3': ('iw3_row_flow_v3_20250627.pth', '2e4daa14a72a5f751ffff489c1809ce2c4c6aea6191d47f67f2f72afe4ef612a'),
    'mlbw_l2s': ('iw3_mlbw_l2s_d1_20250627.pth', 'd66467d9b055bf7ca651aeb24d11d2ccc9ad447d040a5b3e455962821c891e28'),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def models(source, weights):
    assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == REVISION
    assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip()
    sys.path.insert(0, str(source.resolve()))
    classes = {}
    for module, cls in [('row_flow_v3', 'RowFlowV3'), ('mlbw', 'MLBW')]:
        spec = importlib.util.spec_from_file_location('comparison_' + module, source / 'iw3/models' / (module + '.py'))
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
        classes[module] = getattr(loaded, cls)
    result = {}
    for name, (filename, digest) in WEIGHTS.items():
        path = weights / filename
        assert sha(path) == digest, filename
        checkpoint = torch.load(path, map_location='cpu', weights_only=True)
        cls = classes['mlbw' if name == 'mlbw_l2s' else 'row_flow_v3']
        assert checkpoint['name'] == cls.name
        model = cls(**checkpoint['kwargs'])
        model.load_state_dict(checkpoint['state_dict'], strict=True)
        model.delta_output = True
        model.symmetric = name.endswith('_sym')
        result[name] = model.eval().cuda()
    return result


def save_rgb(path, rgb):
    assert cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def label(rgb, title):
    out = np.pad(rgb, ((30, 0), (0, 0), (0, 0)), constant_values=246)
    cv2.putText(out, title, (10, 21), cv2.FONT_HERSHEY_SIMPLEX, .55, (20, 20, 20), 1, cv2.LINE_AA)
    return out


def synthetic():
    w, h = 1280, 720
    yy, xx = np.indices((h, w))
    bg = np.stack((60 + (xx // 24 % 2) * 45, 100 + (yy // 24 % 2) * 45, 140 + (xx // 48 % 2) * 35), -1).astype('uint8')
    for y in range(80, h, 100):
        cv2.putText(bg, 'DEPTH / SMALL TEXT / 0123456789', (30, y), cv2.FONT_HERSHEY_SIMPLEX, .8, (245, 245, 245), 1, cv2.LINE_AA)
    mask = np.zeros((h, w), np.uint8)
    cv2.rectangle(mask, (420, 110), (780, 610), 255, -1)
    for x in (300, 900, 980):
        cv2.rectangle(mask, (x, 100), (x + 3, 620), 255, -1)
    fg = np.full_like(bg, (205, 60, 35))
    cv2.putText(fg, 'NEAR', (460, 350), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3, cv2.LINE_AA)
    rgb = np.where(mask[..., None] != 0, fg, bg)
    depth = np.full((h, w), .45, np.float32)
    depth[mask != 0] = .45 + 8 / (w * .026 * .5)
    eyes, holes = [], []
    for shift in (8, -8):
        matrix = np.float32([[1, 0, shift], [0, 1, 0]])
        moved_mask = cv2.warpAffine(mask, matrix, (w, h), flags=cv2.INTER_NEAREST)
        moved_fg = cv2.warpAffine(fg, matrix, (w, h), flags=cv2.INTER_NEAREST)
        eyes.append(np.where(moved_mask[..., None] != 0, moved_fg, bg))
        holes.append((mask != 0) & (moved_mask == 0))
    return rgb, depth, np.concatenate(eyes, 1), np.concatenate(holes, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT / 'out/iw3-render-source-20261105')
    parser.add_argument('--weights', type=Path, default=ROOT / 'out/iw3-render-models-20261105')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    configure_resource_root(BUNDLE)
    torch.set_num_threads(4)
    loaded = models(args.source, args.weights)
    from iw3.backward_warp import apply_divergence_nn_LR
    policy = resolve_live('balanced')
    report = dict(revision=REVISION, weights=WEIGHTS, attribution=ATTRIBUTION,
                  precision='iw3 upstream autocast FP16; RGB/depth FP32; TF32 disabled',
                  mapping='iw3 divergence = 100 * ScreenTo3D divergence = 2.6; convergence=.45; standard left/right eye order; both eyes; no mapper; no border forcing',
                  scope='Renderer comparison only. Same final depth; no new depth model, GUI integration or headset acceptance.',
                  timings=[], quality=[], calibration=[])
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False

    def inputs(rgb, depth):
        return (torch.from_numpy(rgb).cuda().permute(2, 0, 1)[None].float().div(255),
                torch.from_numpy(depth.copy()).cuda()[None, None])

    def render(name, color, depth):
        left, right = apply_divergence_nn_LR(loaded[name], color, depth, 100 * policy.divergence,
                                           policy.convergence, steps=1, enable_amp=True)
        return left, right

    def pixels(eyes):
        return torch.cat(eyes, dim=3).clamp(0, 1).mul(255).round().to(torch.uint8)[0].permute(1, 2, 0).cpu().numpy()

    def compare(rgb, depth, projection, benchmark=False):
        h, w = depth.shape
        shift = np.ascontiguousarray((depth-policy.convergence) * (w * policy.divergence * .5))
        current = np.concatenate(projection.project_pair(rgb, depth, shift, conservative_coverage=True), 1)
        outputs = {'current_cuda': current}
        for name in loaded:
            c, d = inputs(rgb, depth)
            with torch.inference_mode():
                outputs[name] = pixels(render(name, c, d))
        if benchmark:
            # All CPU timings include identical host input/output boundaries.
            # GPU resident iw3 latency has a different boundary, labelled below.
            for name in outputs:
                cpu, resident = [], []
                for i in range(13):
                    torch.cuda.synchronize()
                    start = time.perf_counter()
                    if name == 'current_cuda':
                        projection.project_pair(rgb, depth, shift, conservative_coverage=True)
                    else:
                        with torch.inference_mode():
                            c, d = inputs(rgb, depth)
                            result = render(name, c, d)
                            pixels(result)
                    if i >= 3:
                        cpu.append((time.perf_counter()-start)*1000)
                if name != 'current_cuda':
                    c, d = inputs(rgb, depth)
                    with torch.inference_mode():
                        for i in range(13):
                            a, b = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                            a.record()
                            render(name, c, d)
                            b.record()
                            b.synchronize()
                            if i >= 3:
                                resident.append(a.elapsed_time(b))
                row = dict(size=[w,h], method=name, cpu_in_out_ms=statistics.median(cpu),
                           resident_gpu_ms=statistics.median(resident) if resident else None,
                           cpu_samples=cpu, resident_samples=resident)
                report['timings'].append(row)
                print(json.dumps(row), flush=True)
        return outputs

    # Constant-plane calibration independently checks eye order and strength.
    rgb = np.zeros((256, 1920, 3), np.uint8)
    rgb[:, 950:971] = 255
    depth = np.full((256,1920), .85, np.float32)
    with LiveProjection(1920,256) as projection:
        values = compare(rgb, depth, projection)
    for name, value in values.items():
        offsets = []
        for eye in np.split(value, 2, 1):
            profile = eye[64:-64,:,0].astype(float).sum(0)
            offsets.append(float(np.dot(profile, np.arange(1920))/profile.sum()-960))
        expected = ((.85-.45)*1920*.026*.5, -(.85-.45)*1920*.026*.5)
        assert max(abs(a-b) for a,b in zip(offsets,expected)) < 1.5, (name,offsets,expected)
        report['calibration'].append(dict(method=name, offsets=offsets, expected=expected))

    rgb, depth, truth, holes = synthetic()
    save_rgb(args.output/'synthetic-source.png', rgb)
    save_rgb(args.output/'synthetic-truth.png', truth)
    np.save(args.output/'synthetic-depth.npy', depth)
    with LiveProjection(1280,720) as projection:
        values = compare(rgb, depth, projection)
    panels = []
    for name, value in values.items():
        save_rgb(args.output/(name+'-synthetic.png'), value)
        error = np.abs(value.astype(float)-truth)
        row = dict(case='synthetic', method=name, mae=float(error.mean()),
                   visible_mae=float(error[~holes].mean()), disocclusion_mae=float(error[holes].mean()))
        report['quality'].append(row)
        panels.append(label(value[80:640, 270:1030], name+' / left eye, original pixels'))
    save_rgb(args.output/'synthetic-comparison.png', np.concatenate(panels,0))

    runtime = Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
    with ExitStack() as stack:
        stack.enter_context(os.add_dll_directory(str(runtime)))
        backend = binding(ROOT/'out/da2-base-local',runtime)
        backend.input_validator(dict(width=1920,height=1080))
        engine = stack.enter_context(backend.engine_factory(None))
        for source_name in SOURCES:
            path = CORPUS/(source_name+'.mp4')
            meta = json.loads(path.with_suffix('.json').read_text())
            assert sha(path)==meta['sha256'] and meta['source_sha256']==SOURCES[source_name]
            video = cv2.VideoCapture(str(path))
            captured = []
            def intercept(frame, aligned, shift, **options):
                captured[:] = [aligned.copy()]
                return frame, frame
            synth = StereoSynthesizer(1920,1080,policy,paired_projection=intercept)
            clipdir = args.output/source_name
            clipdir.mkdir()
            writer = cv2.VideoWriter(str(clipdir/'comparison.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), 60, (1920,600))
            assert writer.isOpened()
            try:
                with LiveProjection(1920,1080) as projection:
                    for i in range(60):
                        ok, bgr = video.read()
                        assert ok
                        rgb = cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
                        synth.render(rgb,engine.infer(rgb))
                        depth = captured[0]
                        values = compare(rgb,depth,projection,benchmark=(source_name=='FloorballGame' and i==0))
                        cells = [label(cv2.resize(value,(960,270)),name) for name,value in values.items()]
                        grid = np.concatenate((np.concatenate(cells[:2],1),np.concatenate(cells[2:],1)),0)
                        writer.write(cv2.cvtColor(grid,cv2.COLOR_RGB2BGR))
                        if i==30:
                            save_rgb(clipdir/'source.png',rgb)
                            np.save(clipdir/'depth.npy',depth)
                            save_rgb(clipdir/'overview.png',grid)
                            for name,value in values.items():
                                save_rgb(clipdir/(name+'.png'),value)
                print(source_name+' 60 identical-input frames finished',flush=True)
            finally:
                video.release()
                writer.release()
        # 4K renderer cost; source is explicitly an upscaled public 1080p frame.
        rgb = cv2.resize(rgb,(3840,2160))
        depth = np.ascontiguousarray(cv2.resize(depth,(3840,2160)),dtype=np.float32)
        with LiveProjection(3840,2160) as projection:
            compare(rgb,depth,projection,benchmark=True)
    report['passed'] = True
    (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
