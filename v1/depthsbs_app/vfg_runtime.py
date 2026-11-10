"""VFG opt-in policy and trusted runtime identity; no GPU/Qt imports."""

from .messages import Message as M
import hashlib
from pathlib import Path

from .desktop_jobs import ROOT
from .portable_cuda import binary

SUPPORTED_MODELS = ('da2-small', 'da2-base')
SDK = ROOT / 'out/vfg-runtime/1.3.0.0'
BRIDGE = ROOT / 'out/vfg-native-bridge-detail/vfg_native_bridge.dll'
BRIDGE_HASH = 'a5f0df818fae26fb8ecd3403cb6965d9cd034f1338121375d10a7461ce0b1671'
BRIDGE, BRIDGE_HASH = binary(BRIDGE, BRIDGE_HASH)
PINS = {
    'bin/NVVideoEffects.dll': 'c6b042fc57bdb6bea88c9c52cb951582377d3f1643acf52a52d197195a1ea8f4',
    'bin/NVCVImage.dll': '689a64586c804468127647b7ed24acc36a9a9780502ffe95ad11aa4fe3286a39',
    'features/nvvfxvideoframegeneration/bin/nvVFXVideoFrameGeneration.dll':
        '270cf4fff9329908f9770d306cb51b910ee04323af5520cd02a98a2e22aba795',
    'bin/nvngxruntime.dll': 'd2dbd1993000a2eed2c7ad8cd417ffc738ea180003daacf190e737121869d637',
    'bin/cudart64_12.dll': '663b5fe65aa6c654b8b085a879f49deb19f2cb033b8f2ff8dffd06cdefe0d1db',
}


def unavailable_reason(model, source_kind, native, gpu, renderer='cuda'):
    if model not in SUPPORTED_MODELS:
        return M('VFG is available with DA2 Small and DA2 Base.')
    if source_kind != 'window':
        return M('VFG is available with window capture.')
    if not native or not gpu:
        return M('VFG requires direct GPU output and GPU capture.')
    if renderer != 'cuda':
        return M('VFG requires the default stereo renderer. Close the RowFlow trial and start the normal launcher.')
    return ''


def validate_selection(enabled, model, source_kind, native, gpu, renderer='cuda'):
    if type(enabled) is not bool:
        raise ValueError('Invalid VFG selection')
    if enabled:
        reason = unavailable_reason(model, source_kind, native, gpu, renderer)
        if reason:
            raise ValueError(reason + M(' Turn off VFG or choose supported settings.'))


def validate_runtime(sdk=None, bridge=None):
    sdk = runtime_path() if sdk is None else Path(sdk)
    bridge = BRIDGE if bridge is None else Path(bridge)
    for path, expected in [(sdk / name, sha) for name, sha in PINS.items()] + [(bridge, BRIDGE_HASH)]:
        if not path.is_file():
            raise RuntimeError(M('VFG components are not ready. Turn off VFG or check the installation.'))
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise RuntimeError(M('VFG component verification failed. Repair the installation, then try again.'))
    return sdk, bridge


def runtime_path():
    from .optional_models import installed_path
    managed = installed_path('vfg')
    return managed if (managed / '.verified').is_file() else SDK
