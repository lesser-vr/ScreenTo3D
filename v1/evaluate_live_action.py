"""CC-BY UVG-VCM preview excerpts; sequential matched diagnostic conversions."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid
from unittest.mock import patch
import cv2
import numpy as np
from evaluate_depth_models import ROOT, sha, inspect_media, run_one
from temporal_diagnostics import TemporalProbe
from vda_comparison import validate_runs, inspection_sheet

SOURCES = {
    'OfficeWalk': 'f5782245401781cd358727a382a74f3e7763880cc855811a716159899cfb41a1',
    'HighwayDrive': '6306019ccd4d55ce4fb32abb162e9ff09d9bdda02607f1df92d0dac566c269d5',
    'FloorballGame': 'e68fce59944a9099df25dc81b145f871f2c370f21fa7b6c81e43fc7d9bceca00',
    'ParkingGarage': 'aabbde5730f95eb6fb681e79da9a4ea544a62e6155e1219514909b60c7451403',
}
MODELS = ('small', 'base', 'vda')
ATTRIBUTION = ('UVG-VCM, Ultra Video Group, Tampere University. CC BY 4.0. '
    'T. Partanen, M. Anttila, R. Kortelahti, G. Gautier, A. Mercat, and J. Vanne, '
    'UVG-VCM: Benchmarking dataset for machine-oriented visual data compression, QoMEX 2026. '
    'https://tie-ultravideo.rd.tuni.fi/UVG-VCM/index.html ; https://creativecommons.org/licenses/by/4.0/ . '
    'Modified: official compressed previews excerpted at 1-3 seconds, scaled 3840x2160 to 1280x720 '
    'without crop/padding, H264 CRF18, original 60fps and absence of audio preserved; '
    'ScreenTo3D AI-estimated SBS derivatives and labeled review crops. No endorsement.')


def worker(args):
    from screento3d_app import pipeline
    probe = TemporalProbe()
    original = pipeline.StereoSynthesizer.render
    cut_parity = []
    def render(renderer, frame, depth):
        cut = renderer.is_scene_cut(frame)
        probe.add(frame, depth, cut=cut)
        result = original(renderer, frame, depth)
        if cut:
            fresh = pipeline.StereoSynthesizer(renderer.width, renderer.height, renderer.policy)
            expected = original(fresh, frame, depth)
            maximum = int(np.max(np.abs(result.astype(np.int16)-expected.astype(np.int16))))
            cut_parity.append(dict(frame=len(probe.rows)-1, fresh_renderer_max_abs=maximum))
            if maximum != 0:
                raise AssertionError('Renderer carries temporal state across cut')
        return result
    with patch.object(pipeline.StereoSynthesizer, 'render', render):
        run_one(argparse.Namespace(input=args.input, output=args.output, one=args.one, hashes=True, memory=False))
    path = args.output.with_suffix('.json')
    report = json.loads(path.read_text())
    report['motion_compensated_depth'] = probe.report()
    report['cut_renderer_fresh_parity'] = cut_parity
    path.write_text(json.dumps(report, indent=2))


def review(folder, frames, fps):
    captures = [cv2.VideoCapture(str(folder/name)) for name in ('input.mp4', 'small.mp4', 'base.mp4', 'vda.mp4')]
    writer = None
    try:
        for index in range(frames):
            reads = [c.read() for c in captures]
            if not all(ok for ok, _ in reads): raise ValueError('Review frame missing')
            source, *outputs = [im for _, im in reads]
            h, w = source.shape[:2]
            # Same central full-height region in both eyes; 2x enlargement, labels outside pixels.
            x0, x1 = w//3, 2*w//3
            rows = []
            for name, im in [('SOURCE', np.concatenate([source, source], axis=1)), *zip(MODELS, outputs)]:
                pair = np.concatenate([im[:, x0:x1], im[:, w+x0:w+x1]], axis=1)
                pair = cv2.resize(pair, (pair.shape[1]*2, pair.shape[0]*2), interpolation=cv2.INTER_NEAREST)
                rows.append((name+' left / right - central boundary crop', pair))
            # inspection_sheet bounds width; full originals remain available.
            sheet = inspection_sheet(rows, (x1-x0)*2, h*2)
            if index in (0, frames//2, frames-1): cv2.imwrite(str(folder/f'edges-{index}.jpg'), sheet)
            # Review video is 800px wide to keep software playback affordable.
            small = cv2.resize(sheet, (800, round(sheet.shape[0]*800/sheet.shape[1])//2*2))
            if writer is None:
                writer = cv2.VideoWriter(str(folder/'boundary-review.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), fps, (small.shape[1], small.shape[0]))
                if not writer.isOpened(): raise RuntimeError('Review writer failed')
            writer.write(small)
    finally:
        for capture in captures: capture.release()
        if writer is not None: writer.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--one', choices=MODELS)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--prepared', type=Path)
    args = parser.parse_args()
    if args.one: worker(args); return
    from screento3d_app import pipeline
    from screento3d_app.resources import configure_media_tools
    media = ROOT/'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal/ffmpeg'
    configure_media_tools(media)
    root = args.prepared or ROOT/'out/live-action-evaluation'/uuid.uuid4().hex
    if args.prepared:
        report = json.loads((root/'report.json').read_text())
    else:
        root.mkdir(parents=True)
        report = dict(passed=False, attribution=ATTRIBUTION, clips=[],
                      scope='Short diagnostic comparison, not sustained performance or ground-truth depth evaluation')
        (root/'ATTRIBUTION.txt').write_text(ATTRIBUTION)
        for name, expected in SOURCES.items():
            source = ROOT/'out/public-video-source/uvg-vcm'/f'{name}.mp4'
            if sha(source) != expected: raise ValueError('Source hash mismatch: '+name)
            folder = root/name; folder.mkdir()
            clip = folder/'input.mp4'
            subprocess.run([str(media/'ffmpeg.exe'), '-v', 'error', '-ss', '1', '-i', str(source),
                '-t', '2', '-map', '0:v:0', '-vf', 'scale=1280:720:flags=lanczos',
                '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', str(clip)], check=True)
            meta = pipeline.probe_video(clip)
            assert (meta['width'], meta['height'], meta['total_frames'], meta['fps'], meta['has_audio']) == (1280, 720, 120, 60, False)
            report['clips'].append(dict(name=name, source_sha256=expected,
                source_url=f'https://tie-ultravideo.rd.tuni.fi/UVG-VCM/{name}/{name}.mp4',
                input_sha256=sha(clip), metadata=meta, runs={}))
        # Annotated hard cut: first second OfficeWalk followed by first second ParkingGarage.
        folder = root/'KnownCut'; folder.mkdir()
        subprocess.run([str(media/'ffmpeg.exe'), '-v', 'error', '-i', str(root/'OfficeWalk/input.mp4'),
            '-i', str(root/'ParkingGarage/input.mp4'), '-filter_complex',
            '[0:v]trim=end_frame=60,setpts=PTS-STARTPTS[a];[1:v]trim=end_frame=60,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0[v]',
            '-map', '[v]', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', str(folder/'input.mp4')], check=True)
        report['clips'].append(dict(name='KnownCut', annotated_cut_frame=60,
            input_sha256=sha(folder/'input.mp4'), metadata=pipeline.probe_video(folder/'input.mp4'), runs={}))
        # Source contact sheet for selection, before expensive conversions.
        tiles = []
        for item in report['clips']:
            capture = cv2.VideoCapture(str(root/item['name']/'input.mp4'))
            for index in (0, 60, 119):
                capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = capture.read(); assert ok
                tile = cv2.resize(frame, (480, 270))
                cv2.putText(tile, item['name']+f' frame {index}', (8, 24), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 255), 1)
                tiles.append(tile)
            capture.release()
        cv2.imwrite(str(root/'source-contact.jpg'), np.concatenate([np.concatenate(tiles[i:i+3], axis=1) for i in range(0, len(tiles), 3)], axis=0))
    print(root, flush=True)
    try:
        if args.prepare_only: return
        for item in report['clips']:
            folder = root/item['name']
            assert sha(folder/'input.mp4') == item['input_sha256']
            for model in MODELS:
                output = folder/f'{model}.mp4'
                if output.exists(): raise ValueError('Refusing to overwrite existing result')
                with (folder/f'{model}.log').open('w') as log:
                    subprocess.run([sys.executable, __file__, '--one', model, '--input', str(folder/'input.mp4'),
                        '--output', str(output)], check=True, stdout=log, stderr=subprocess.STDOUT)
                item['runs'][model] = json.loads(output.with_suffix('.json').read_text())
                inspect_media(output, item['metadata'])
                print('PASS '+item['name']+' / '+model, flush=True)
            validate_runs(item['runs'], 120, 120)
            cuts = [[r['frame'] for r in run['motion_compensated_depth']['rows'] if r['cut']] for run in item['runs'].values()]
            assert cuts[0] == cuts[1] == cuts[2]
            if 'annotated_cut_frame' in item:
                assert item['annotated_cut_frame'] in cuts[0], 'Known cut missed'
            review(folder, 120, 60)
        report['passed'] = True
    finally:
        (root/'report.json').write_text(json.dumps(report, indent=2))
        print(root/'report.json', flush=True)


if __name__ == '__main__': main()
