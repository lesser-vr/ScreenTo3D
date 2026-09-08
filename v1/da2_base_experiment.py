"""Pinned non-commercial DA2 Base CUDA oracle; not a public app backend."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import threading

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REVISION = 'a561b849ebae10a6f5ef49e26c83cbbcd36c71bf'
WEIGHT_REVISION = 'a4e71a6c2ce52fe50df0f212066b0d4a87be9b5e'
WEIGHT_SHA256 = '0d2b7002e62d39d655571c371333340bd88f67ab95050c03591555aa05645328'


def validate_frame(frame):
    if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or
            frame.ndim != 3 or frame.shape[2] != 3 or
            not all(16 <= n <= 1920 for n in frame.shape[:2]) or
            max(frame.shape[:2]) > 2 * min(frame.shape[:2])):
        raise ValueError('DA2 Base oracle requires uint8 RGB, 16..1920 dimensions, aspect ratio <=2')


def upstream_class(source=ROOT/'out/da2-base-source'):
    source = source.resolve(strict=True)
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != SOURCE_REVISION:
        raise ValueError('Unexpected DA2 Base source revision')
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip():
        raise ValueError('DA2 Base source must be clean')
    if importlib.util.find_spec('xformers') is not None:
        raise ValueError('Oracle requires native PyTorch attention without xFormers')
    sys.path.insert(0, str(source))
    previous_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        from depth_anything_v2 import dpt
        if not Path(dpt.__file__).resolve().is_relative_to(source):
            raise ValueError('Conflicting DA2 import')
        return dpt.DepthAnythingV2
    finally:
        sys.dont_write_bytecode = previous_bytecode
        sys.path.remove(str(source))


class Da2BaseOracle:
    def __init__(self, progress=None):
        import torch
        self.torch, self.owner = torch, threading.get_ident()
        self.model, self.closed, self.calls = None, False, 0
        if not torch.cuda.is_available():
            raise RuntimeError('DA2 Base oracle requires CUDA; no CPU fallback')
        self.device = torch.cuda.current_device()
        self.last_shape = None
        try:
            cls = upstream_class()
            path = ROOT/'out/models/da2-base/depth_anything_v2_vitb.pth'
            with path.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != WEIGHT_SHA256:
                    raise ValueError('DA2 Base weight checksum mismatch')
            self.model = cls(encoder='vitb', features=128, out_channels=[96, 192, 384, 768])
            self.model.load_state_dict(torch.load(path, map_location='cpu', weights_only=True), strict=True)
            self.model.to(f'cuda:{self.device}').eval()
        except BaseException:
            self.close()
            raise

    def _check(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('DA2 Base must be used/closed by its owner thread')
        if self.closed:
            raise RuntimeError('DA2 Base oracle is closed')
        if self.torch.cuda.current_device() != self.device:
            raise RuntimeError('DA2 Base CUDA device changed')

    def infer(self, frame):
        self._check()
        validate_frame(frame)
        # Upstream expects BGR and performs its own aspect-preserving RGB transform.
        with self.torch.inference_mode(), self.torch.autocast('cuda', enabled=False):
            tensor, (h, w) = self.model.image2tensor(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), 518)
            self.last_shape = list(tensor.shape)
            depth = self.model(tensor.float())
            depth = self.torch.nn.functional.interpolate(depth[:, None], (h, w),
                mode='bilinear', align_corners=True)[:, 0]
            result = depth.cpu().numpy().astype(np.float32, copy=True)
        if result.shape != (1, h, w) or not np.isfinite(result).all():
            raise ValueError('Invalid DA2 Base depth output')
        self.calls += 1
        return result

    def telemetry(self):
        self._check()
        return dict(runtime='pytorch-cuda-fp32', model_id='da2-base', completed_inferences=self.calls,
                    input_shape=self.last_shape, source_revision=SOURCE_REVISION,
                    weight_revision=WEIGHT_REVISION, weight_sha256=WEIGHT_SHA256,
                    weight_license='CC-BY-NC-4.0', zero_copy=False)

    def close(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('DA2 Base must be closed by its owner thread')
        if self.closed:
            return
        try:
            self.torch.cuda.synchronize(self.device)
        finally:
            self.model = None
            self.closed = True

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *exc):
        self.close()
