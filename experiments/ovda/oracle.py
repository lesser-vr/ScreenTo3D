# Cache update derived from oVDA, Copyright (c) 2026 Heidelberg University.
# Licensed under NC-SA-UHDV1.0; see LICENSE in this directory.
# ScreenTo3D modifications: bounded one-frame adapter, validation, lifecycle/telemetry.
"""Pinned personal non-commercial CUDA FP32 oracle; never an automatic fallback."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import threading

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'out/ovda-source'
REVISION = '4173c24e22f528062a0cf8ae235c58a5d4376a74'
WEIGHT_REVISION = '9eda2255e19c51dd1989b9c08b886e665f15007e'
WEIGHT_HASH = 'ea531d53a1135a443bafcf106a175b26a6519c05ccc1e994d74e46159e14b7cb'
WEIGHT_HASH_C8 = 'af3788fbc6517704d3430ee1886f27e648b8d61e2da10b739b3bb59f4e8f585d'


def schedule(used, capacity=16):
    if type(used) is not int or not 0 <= used < capacity or capacity not in (8, 16):
        raise ValueError('Invalid oVDA cache position')
    if used == 0:
        return list(range(1, capacity)), [0, 1]
    return list(range(used, capacity))+[capacity-1]*(used-1), [used, used]


def validate_frame(frame):
    if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
            or frame.ndim != 3 or frame.shape[2] != 3
            or not (16 <= frame.shape[1] <= 4096 and 16 <= frame.shape[0] <= 2160)
            or not 1.30 <= frame.shape[1]/frame.shape[0] <= 1.78):
        raise ValueError('oVDA requires uint8 RGB landscape width 16..4096, height 16..2160 and a validated profile')


def upstream():
    if subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('Unexpected oVDA source revision')
    if subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain'], text=True).strip():
        raise ValueError('oVDA source must be clean')
    if importlib.util.find_spec('xformers') is not None:
        raise ValueError('Pinned experiment requires native attention, no xFormers')
    sys.path.insert(0, str(SOURCE))
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        from src.models import video_depth
        from src.models.utils.preprocessing import VideoPreprocessor
        if not Path(video_depth.__file__).resolve().is_relative_to(SOURCE.resolve()):
            raise ValueError('Conflicting upstream module import')
        return video_depth.onlineVideoDepthAnything, VideoPreprocessor
    finally:
        sys.dont_write_bytecode = previous
        sys.path.remove(str(SOURCE))


class OvdaOracle:
    def __init__(self, progress=None, cache_size=16):
        if cache_size not in (8,16) or type(cache_size) is not int:raise ValueError('Cache size must be 8 or 16')
        self.capacity=cache_size
        self.weight_hash=WEIGHT_HASH if cache_size==16 else WEIGHT_HASH_C8
        import torch
        self.torch = torch
        self.owner = threading.get_ident()
        self.device = torch.cuda.current_device() if torch.cuda.is_available() else None
        self.closed = False
        self.model = self.pre = self.cache = None
        self.shape = None
        self.calls = self.resets = self.used = self.cache_bytes = 0
        if self.device is None:
            raise RuntimeError('oVDA requires CUDA; no CPU fallback')
        try:
            cls, pre = upstream()
            weights = ROOT/f'out/models/ovda/oVDA_c{cache_size}.pth'
            with weights.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != self.weight_hash:
                    raise ValueError('oVDA weights checksum mismatch')
            self.model = cls(encoder='vits', features=64, out_channels=[48,96,192,384],
                             cache_size=cache_size, pe='ape', use_xformers=False)
            self.model.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True), strict=True)
            self.model.to(f'cuda:{self.device}').float().eval()
            self.pre = pre(input_size=518, device='cpu', ensure_multiple_of=14,
                           keep_aspect_ratio=True, resize_method='lower_bound')
        except BaseException:
            self.close()
            raise

    def check(self):
        if threading.get_ident() != self.owner: raise RuntimeError('oVDA owner thread changed')
        if self.closed: raise RuntimeError('oVDA oracle is closed')
        if self.torch.cuda.current_device() != self.device: raise RuntimeError('oVDA CUDA device changed')

    def reset(self, reason):
        self.check()
        if reason not in ('start', 'scene_cut', 'source_change', 'discontinuity'):
            raise ValueError('Invalid reset reason')
        self.torch.cuda.synchronize(self.device)
        self.cache = self.shape = None
        self.used = self.cache_bytes = 0
        self.resets += 1

    def infer(self, frame):
        self.check()
        validate_frame(frame)
        if self.shape is not None and frame.shape != self.shape:
            raise ValueError('Input geometry changed without reset')
        torch = self.torch
        with torch.inference_mode(), torch.autocast('cuda', enabled=False):
            # Decoder buffers may be read-only; upstream wraps NumPy with torch.
            tensor = self.pre.preprocess(frame.copy()).to(f'cuda:{self.device}').float()
            h, w = tensor.shape[-2:]
            if (h, w) not in ((518,686), (518,896), (518,924)):
                raise ValueError('Unvalidated oVDA experiment input profile')
            if self.cache is None:
                self.cache = self.model.setup_cache(h, w, f'cuda:{self.device}')
                self.shape = frame.shape
                self.cache_bytes = sum(v.numel()*v.element_size() for v in self.cache.values())
            mask, position = schedule(self.used,self.capacity)
            depth, new = self.model(tensor, self.cache, torch.tensor(mask, device=tensor.device),
                                    torch.tensor(position, device=tensor.device))
            # Match official c16 cache warm-up and sliding-window semantics exactly.
            if self.used == self.capacity-1:
                self.cache = {k: torch.cat([v[:,:,:,1:self.capacity-1,:], new[k], torch.zeros_like(new[k])], dim=3)
                              for k,v in self.cache.items()}
            else:
                for key in self.cache:
                    self.cache[key][:,:,:,self.used,:] = new[key][:,:,:,0,:]
            self.used = min(self.used+1, self.capacity-1)
            if sum(v.numel()*v.element_size() for v in self.cache.values()) != self.cache_bytes:
                raise RuntimeError('oVDA cache grew unexpectedly')
            if not all(bool(torch.isfinite(v).all()) for v in self.cache.values()):
                raise ValueError('Non-finite oVDA cache')
            result = torch.nn.functional.interpolate(depth, frame.shape[:2], mode='bilinear', align_corners=True)
            result = result[:,0].cpu().numpy().astype(np.float32, copy=True)
        if result.shape != (1,*frame.shape[:2]) or not np.isfinite(result).all():
            raise ValueError('Invalid oVDA depth')
        self.calls += 1
        return result

    def telemetry(self):
        self.check()
        return dict(model_id=f'ovda-small-c{self.capacity}', runtime='pytorch-cuda-fp32-experiment',
                    source_revision=REVISION, weight_revision=WEIGHT_REVISION, weight_sha256=self.weight_hash,
                    license='NC-SA-UHDV1.0', completed_inferences=self.calls, resets=self.resets,
                    cache_slots=self.capacity, cache_used=self.used, cache_bytes=self.cache_bytes, zero_copy=False)

    def close(self):
        if threading.get_ident() != self.owner: raise RuntimeError('oVDA close requires owner thread')
        if self.closed: return
        try:
            if self.device is not None: self.torch.cuda.synchronize(self.device)
        finally:
            self.cache = self.model = self.pre = None
            self.closed = True

    def __enter__(self): self.check(); return self
    def __exit__(self, *exc): self.close()
