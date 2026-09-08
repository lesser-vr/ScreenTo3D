"""Generate bounded 48-frame codec fixtures under a unique ignored directory."""
import json
from pathlib import Path
import subprocess
import uuid
from quality_scenes import motion_frame


def main():
    repo = Path(__file__).resolve().parents[1]
    root = repo / 'out/quality-fixtures' / uuid.uuid4().hex
    root.mkdir(parents=True)
    ffmpeg = repo / 'out/release/DepthSBS/_internal/ffmpeg/ffmpeg.exe'
    for codec, encoder in (('h264', 'libx264'), ('hevc', 'libx265')):
        output = root / f'motion-{codec}.mp4'
        with (root / f'{codec}-encode.log').open('wb') as log:
            process = subprocess.Popen([str(ffmpeg), '-n', '-v', 'error',
                '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '640x360', '-r', '24',
                '-i', '-', '-an', '-c:v', encoder, '-preset', 'fast', '-crf', '18',
                '-pix_fmt', 'yuv420p', str(output)], stdin=subprocess.PIPE, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                for index in range(48):
                    process.stdin.write(motion_frame(index)[0].tobytes())
                process.stdin.close()
                if process.wait(timeout=120):
                    raise RuntimeError(f'Fixture encoding failed: {codec}')
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
                process.stdin.close()
    (root / 'manifest.json').write_text(json.dumps({
        'frames': 48, 'fps': 24, 'width': 640, 'height': 360,
        'cut_frame_zero_based': 25, 'motion_pixels_per_frame': 23,
        'audio': False, 'generator': 'v1/quality_scenes.py',
        'purpose': 'Media/cut smoke; inferred-depth quality is not an oracle'
    }, indent=2), encoding='utf-8')
    print(root)


if __name__ == '__main__':
    main()
