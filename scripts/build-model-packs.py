"""Package the exact ONNX graphs and numeric references used by the local builder."""
import argparse
import hashlib
import shutil
import tempfile
from pathlib import Path
from zipfile import ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
BASE_NOTICE = """Depth Anything V2 Base weights by the Depth Anything V2 authors.
https://huggingface.co/depth-anything/Depth-Anything-V2-Base
CC BY-NC 4.0: https://creativecommons.org/licenses/by-nc/4.0/
DepthSBS converted these weights to mixed-FP16 ONNX for local TensorRT compilation.
"""


def build(directory):
    directory.mkdir(parents=True, exist_ok=True)
    from depthsbs_app.optional_models import GRAPH_HASHES, PACKS
    for model in ('da2-base', 'vda-small'):
        files = {}
        for width in (896, 924):
            profile = f'518x{width}-fp16'
            for stage, digest in GRAPH_HASHES[model][width].items():
                if model == 'da2-base':
                    suffix = '-896' if width == 896 else ''
                    choices = [ROOT/'out'/f'base-trt-fp16{suffix}-20261105/mixed.onnx']
                else:
                    choices = [ROOT/'out/vda-spatial-b8fc5e47/engines'/profile/f'{stage}.onnx']
                for source in choices:
                    with source.open('rb') as stream:
                        if hashlib.file_digest(stream, 'sha256').hexdigest() == digest:
                            files[f'{profile}/{stage}.onnx'] = source
                            break
                else:
                    raise ValueError(f'Missing validated ONNX: {model} {width} {stage}')
            ref = 'vda-small-spatial' if model == 'vda-small' else model
            files[f'{profile}/reference.npz'] = ROOT/'models/engine-reference'/f'{ref}-{width}.npz'
        if model == 'vda-small':
            files['LICENSE.txt'] = ROOT/'out/vda-source/LICENSE'
        with tempfile.TemporaryDirectory(dir=directory) as staging:
            archive = Path(staging) / PACKS[model].filename
            with ZipFile(archive, 'w') as package:
                if model == 'da2-base':
                    package.writestr(ZipInfo('NOTICE.txt'), BASE_NOTICE.encode())
                else:
                    package.writestr(ZipInfo('NOTICE.txt'), b'Video Depth Anything Small (DepthAnything/Video-Depth-Anything), Apache-2.0. DepthSBS adapted the ONNX graphs for streaming TensorRT inference with mixed FP16 encoder projections and spatial attention.\n')
                for name, source in sorted(files.items()):
                    with source.open('rb') as src, package.open(ZipInfo(name), 'w') as dst:
                        shutil.copyfileobj(src, dst)
            with archive.open('rb') as src:
                digest = hashlib.file_digest(src, 'sha256').hexdigest()
            if digest != PACKS[model].sha:
                raise ValueError(f'Pack differs from release pin: {model} {digest}')
            archive.replace(directory / archive.name)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT / 'v1'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    build(parser.parse_args().directory)
