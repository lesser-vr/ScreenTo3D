"""Release binaries compiled from the same ABI with SM120 and compute_75 PTX."""
from .desktop_jobs import ROOT

DIRECTORY = ROOT/'out/portable-cuda'
PINS = {
    'flat_background.dll': 'a3b630bf03b0975647a39965896dcb5e407fed0a1de6ec07dbe92d40da0140ad',
    'vda_input.dll': '491a5cc294920e7e1bc55a30bb1362ea3b6f9079861d2356cfeb3d70c8b1d2ea',
    'live_depth.dll': '205bfa0df9ed5c1969e4c6759f680f94d426fdcd46a3730179965102bc044b8c',
    'small_input.dll': '1a88a09d14f46b9af6e7665aa82621bf51d3d807ce39d58954359a75faf5eb1d',
    'live_texture_runtime.dll': '75b2796f1f3813df01fe5086b59735036906012985bf09331baa4772f648eeeb',
    'base_input.dll': 'd02aa72d503bfed8e0fa32113738c4c3fc1f742140336fed83bbd0e3f1d1c05f',
    'projection.dll': '9f24bdec0f7529a3c596822a2529746d3a74c4481a82f04529fb2cab311e072c',
    'live_motion.dll': '7f462655a7951f037e8f13fabc63f4cc4b4e61c7fcef8c47bd69805dbb5b0e0c',
    'vfg_native_bridge.dll': '3a1a9184c2eb5b920c04c7bc96b8e421dfc8c492c57e272e0c92d4e15ae7c8f7',
}

_PRODUCTION_DIRS = {'static-sbs', 'base-input', 'live-motion-static', 'vfg-native-bridge-detail',
                    'cuda-projection-preview'}


def binary(path, legacy_hash):
    production = (path.parent.parent == ROOT/'out' and path.parent.name in _PRODUCTION_DIRS
                  or path == ROOT/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/projection/projection.dll')
    if production and DIRECTORY.is_dir() and path.name in PINS:
        return DIRECTORY/path.name, PINS[path.name]
    return path, legacy_hash
