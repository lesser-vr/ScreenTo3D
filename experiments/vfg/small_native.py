"""Lazy Small adapter; only worker/explicit GPU checks load TensorRT."""
from screento3d_app.live_small_gpu_input import LiveSmallGpuInput
from native_path import VfgOutputMixin, SMALL_LAYOUT_HASH


class SmallVfgRenderer(VfgOutputMixin, LiveSmallGpuInput):
    expected_model = 'da2-small'
    expected_layout = SMALL_LAYOUT_HASH
