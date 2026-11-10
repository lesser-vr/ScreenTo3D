"""Local live-SBS comparison using the measured RTX 5090 spatial-attention plans."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
LOCAL_CACHE = ROOT / 'out/vda-mixed-encoder-20261108/install-qa'
TRIAL = ROOT / 'out/vda-spatial-b8fc5e47/engines'
DEVICE_KEY = '74387b40ebfcd9e4990837e4'
PINS = {
    '518x896-fp16': '429b817b7b2679578874b49d2d8b1a22ac6bc81bf431217e208dff75a7e2d172',
    '518x924-fp16': 'bad1dfa15b7f5d45cb25fe4c8c7ece2a7748dac3b37596e14a0628f29054303b',
}


def trial_record(profile):
    data = (TRIAL / profile / 'trial.json').read_bytes()
    if hashlib.sha256(data).hexdigest() != PINS[profile]:
        raise ValueError('시험 엔진의 빌드 기록이 측정 당시와 다릅니다.')
    return json.loads(data)


def spatial_sbs_worker(*args, **kwargs):
    from depthsbs_app import live_sbs, vda_backend
    from depthsbs_app.engine_cache import device_identity, device_key
    from depthsbs_app.optional_models import installed_path
    import torch

    original_init = vda_backend.VdaEngine.__init__
    release_root = installed_path('vda-small').resolve(strict=True)

    def load_spatial(engine, directory, runtime_dir, progress=None):
        directory = Path(directory).resolve(strict=True)
        if directory.parent != release_root or directory.name not in PINS:
            raise ValueError('이 시험은 준비된 VDA Small 프로필만 지원합니다.')
        if device_key(device_identity(torch.cuda.current_device())) != DEVICE_KEY:
            raise ValueError('GPU 또는 드라이버가 시험 엔진을 빌드한 환경과 다릅니다.')
        metadata = dict(vda_backend.load_manifest(directory), engines=trial_record(directory.name),
                        validation='experimental-spatial-attention')
        # Only this live worker opens the trial plans. VdaEngine rehashes the actual
        # bytes before deserialization and checks device, runtime and tensor contracts.
        with patch.object(vda_backend, 'load_manifest', return_value=metadata):
            original_init(engine, TRIAL / directory.name, runtime_dir, progress)
        if sys.stdout is not None:
            print(f'Loaded spatial FP16 live engine: {engine.directory}', flush=True)

    with patch.object(vda_backend.VdaEngine, '__init__', load_spatial):
        return live_sbs.sbs_worker(*args, **kwargs)


def create_comparison(baseline):
    os.environ['LOCALAPPDATA'] = str(LOCAL_CACHE)
    os.environ['DEPTHSBS_GPU_CAPTURE'] = '1'
    os.environ['DEPTHSBS_STEREO_RENDERER'] = 'cuda'
    from depthsbs_app import live_sbs
    from depthsbs_app.desktop import create_app
    from depthsbs_app.engine_cache import device_identity, device_key
    from depthsbs_app.optional_models import available, installed_path

    directory = installed_path('vda-small')
    if not available('vda-small', directory) or device_key(device_identity()) != DEVICE_KEY:
        raise RuntimeError('이 PC에서 측정한 VDA Small 모델 캐시 또는 GPU 구성을 확인할 수 없습니다.')
    if not baseline:
        for profile in PINS:
            for record in trial_record(profile).values():
                with (TRIAL / profile / record['file']).open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != record['sha256']:
                        raise ValueError('VDA 시험 엔진 파일의 체크섬이 일치하지 않습니다.')
        live_sbs.sbs_worker = spatial_sbs_worker
    from depthsbs_app import live_preview
    from PySide6.QtCore import Slot
    sys.path.insert(0, str(ROOT / 'experiments/vfg'))
    from owl_output import OwlOutputLive

    class VdaWindowLive(OwlOutputLive):
        @Slot()
        def start(self):
            if self.kind != 'window':
                self.reportError('원본 게임 또는 영상 창을 입력으로 선택하세요.')
                return
            super().start()

    with patch.object(live_preview, 'LivePreview', VdaWindowLive):
        app, scene, desktop = create_app()
    live = desktop.live
    live.output_window.setTransientParent(None)
    live.setMode('video-quality')
    live.setLiveModel('vda-small')
    live.setProcessingPath('gpu-texture')
    live.setVfg(False)
    live.setStrength(0.5)
    live.setPresentationHz(60)
    label = '배포판 v2' if baseline else '공간 어텐션 FP16 시험판'
    desktop.main_window.setTitle(f'DepthSBS · Owl3D · {label}')
    return app, scene, desktop


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    try:
        app, scene, desktop = create_comparison(args.baseline)
    except Exception as error:
        from ctypes import windll
        windll.user32.MessageBoxW(None, str(error), 'DepthSBS · VDA 실행 오류', 0x10)
        return 1
    try:
        return app.exec()
    finally:
        import shiboken6
        shiboken6.delete(scene)


if __name__ == '__main__':
    raise SystemExit(main())
