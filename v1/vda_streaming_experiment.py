"""Pinned, development-only VDA Small CUDA oracle adapter; not registered in UI."""
import gc
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import threading

import numpy as np

SOURCE_REVISION = '4f5ae23172ba60fd7bc11ef671cca678842c7072'
WEIGHT_REVISION = '256875362cff76724b920335dfb4b29dd611f66e'
WEIGHT_SHA256 = '13379300b739e659f076a59d52e9801bd8d38c541a7e71f73bbca4dcfb013609'
ROOT = Path(__file__).resolve().parents[1]


def upstream_class(source=ROOT / 'out/vda-source'):
    source = source.resolve(strict=True)
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != SOURCE_REVISION:
        raise ValueError('Unexpected VDA source revision')
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip():
        raise ValueError('VDA source worktree must be clean')
    sys.path.insert(0, str(source))
    try:
        from video_depth_anything import video_depth_stream
        if not Path(video_depth_stream.__file__).resolve().is_relative_to(source):
            raise RuntimeError('Conflicting VDA import path')
        return video_depth_stream.VideoDepthAnything
    finally:
        sys.path.remove(str(source))


def checked_weights(path=ROOT / 'out/models/vda-small/video_depth_anything_vits.pth'):
    import torch
    path = path.resolve(strict=True)
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != WEIGHT_SHA256:
            raise ValueError('VDA Small weight checksum mismatch')
    return torch.load(path, map_location='cpu', weights_only=True)


class VdaStreamingEngine:
    def __init__(self, progress=None, *, input_size=518):
        if input_size not in (140, 518):
            raise ValueError('Only explicitly tested oracle sizes 140/518 are allowed')
        import torch
        if importlib.util.find_spec('xformers') is not None:
            raise RuntimeError('Pinned oracle requires native PyTorch attention, without xFormers')
        self.torch = torch
        self.owner = threading.get_ident()
        self.model = None
        self.closed = False
        self.input_size = input_size
        self.shape = None
        self.calls = self.resets = self.peak_cache_entries = 0
        if not torch.cuda.is_available():
            raise RuntimeError('VDA experiment requires CUDA; no CPU fallback')
        self.device = torch.cuda.current_device()
        try:
            model_class = upstream_class()
            self.model = model_class(encoder='vits', features=64, out_channels=[48, 96, 192, 384])
            self.model.load_state_dict(checked_weights(), strict=True)
            self.model = self.model.to(f'cuda:{self.device}').eval()
        except BaseException as primary:
            try:
                self.close()
            except Exception as cleanup:
                primary.add_note(f'VDA cleanup: {cleanup}')
            raise

    def _check(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('VDA must be used and closed by its owner thread')
        if self.closed:
            raise RuntimeError('VDA is closed')
        if self.torch.cuda.current_device() != self.device:
            raise RuntimeError('VDA CUDA device changed')

    def reset(self, reason):
        self._check()
        if reason not in ('start', 'scene_cut', 'source_change', 'discontinuity'):
            raise ValueError('Invalid VDA reset reason')
        self.torch.cuda.synchronize(self.device)
        self.model.frame_cache_list.clear()
        self.model.frame_id_list.clear()
        self.model.transform = None
        self.model.id = -1
        self.shape = None
        self.resets += 1

    def infer(self, frame):
        self._check()
        if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or
                frame.ndim != 3 or frame.shape[2] != 3 or
                not all(16 <= value <= 1920 for value in frame.shape[:2])):
            raise ValueError('VDA oracle requires uint8 RGB, dimensions 16..1920')
        if self.shape is not None and self.shape != frame.shape:
            raise ValueError('Reset VDA before changing source dimensions')
        try:
            output = self.model.infer_video_depth_one(frame, input_size=self.input_size,
                device='cuda', fp32=False)
            result = np.array(output, dtype=np.float32, copy=True)[None]
            if result.shape != (1, *frame.shape[:2]) or not np.isfinite(result).all():
                raise RuntimeError('VDA produced invalid depth')
            entries = len(self.model.frame_cache_list)
            if entries > self.model.gap + 1 or len(self.model.frame_id_list) != entries:
                raise RuntimeError('VDA cache exceeded pinned-source bound')
            self.peak_cache_entries = max(self.peak_cache_entries, entries)
            self.calls += 1
            self.shape = frame.shape
            return result
        except BaseException as primary:
            try:
                self.close()
            except Exception as cleanup:
                primary.add_note(f'VDA cleanup: {cleanup}')
            raise

    def telemetry(self):
        self._check()
        return dict(scope='PyTorch development oracle; allocator is process-global',
            completed_inferences=self.calls, resets=self.resets,
            cache_entries=len(self.model.frame_cache_list), peak_cache_entries=self.peak_cache_entries,
            cache_entry_limit=42, cuda_allocated_bytes=self.torch.cuda.memory_allocated(self.device),
            cuda_reserved_bytes=self.torch.cuda.memory_reserved(self.device),
            input_size=self.input_size, xformers=False, zero_copy=False,
            source_revision=SOURCE_REVISION, checkpoint_sha256=WEIGHT_SHA256)

    def close(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('VDA must be closed by its owner thread')
        if self.closed:
            return
        self.closed = True
        try:
            self.torch.cuda.synchronize(self.device)
        finally:
            self.model = None
            self.shape = None
            gc.collect()

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, kind, value, traceback):
        try:
            self.close()
        except Exception as cleanup:
            if value is None:
                raise
            value.add_note(f'VDA cleanup: {cleanup}')
        return False


def binding(input_size=518):
    from screento3d_app.depth_backend import BackendBinding, BackendSpec
    return BackendBinding(BackendSpec('vda-small-streaming-experimental', 'pytorch-cuda',
        stateful=True, requires_every_frame=True),
        lambda progress: VdaStreamingEngine(progress, input_size=input_size), lambda frame: frame)
