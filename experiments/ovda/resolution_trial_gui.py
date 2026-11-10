# oVDA personal/non-commercial trial, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Explicit live-only comparison GUI; normal loader/defaults remain unchanged."""
import argparse
import json
from functools import partial
from pathlib import Path
import sys
from unittest.mock import patch
from trial_runtime import live_trial_worker,selected


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',choices=('fp32-current','encoder-spatial','low-fp32','low-fp16'),required=True)
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    with selected(args.variant):pass # Verify pinned bytes before creating a UI.
    from depthsbs_app.desktop_jobs import ROOT
    from depthsbs_app import desktop as desktop_module,live_sbs,model_presentation
    from depthsbs_app.desktop_preferences import DesktopPreferences
    from PySide6.QtCore import QSettings
    import shiboken6
    folder=args.output or ROOT/'out/ovda-resolution-20261109/manual'/args.variant
    folder.mkdir(parents=True,exist_ok=True)
    preferences=DesktopPreferences(QSettings(str((folder/'preferences.ini').resolve()),QSettings.IniFormat))
    original_create=desktop_module.create_app;original_info=model_presentation.model_info
    low=args.variant.startswith('low-');mixed=args.variant in ('encoder-spatial','low-fp16')
    label=f'oVDA {"392x700" if low else "518x924"} {"FP16 혼합" if mixed else "FP32"} 시험'
    def create_app(*values,**options):
        app,engine,controller=original_create(preferences=preferences)
        controller.main_window.setTitle('ScreenTo3D · '+label)
        controller.live.output_placement.path=folder/'placement.json'
        return app,engine,controller
    def model_info(model,engine=''):
        if model!='ovda-small-c16':return original_info(model,engine)
        return 'oVDA c16 · 시험','FP16 혼합' if mixed else 'FP32 실시간 / FP16 파일',(
            label+'\n\n실시간 SBS 비교 경로입니다. 시간축 처리와 캐시·출력은 FP32입니다. '
            '파일 변환은 채택된 518×924 혼합 FP16 경로를 사용합니다. 개인·비상업적 사용 조건을 확인하세요.')
    with patch.object(live_sbs,'sbs_worker',partial(live_trial_worker,args.variant)),\
         patch.object(desktop_module,'create_app',create_app),patch.object(model_presentation,'model_info',model_info):
        if args.verify:
            if args.output is None:parser.error('--verify requires --output')
            import test_sbs_start
            sys.argv=[sys.argv[0],'--path','gpu-texture','--mode','video-quality','--model','ovda-small-c16',
                      '--noncommercial','--layout','half-tb','--source-size','1280','720','--resize-input',
                      '--output',str(folder/'lifecycle')]
            test_sbs_start.main()
            report_path=folder/'lifecycle/report.json'
            report=json.loads(report_path.read_text())
            report.update(trial_variant=args.variant,canvas=[392,700] if low else [518,924],mixed_fp16=mixed)
            report_path.write_text(json.dumps(report,indent=2))
        else:
            app,engine,controller=create_app()
            controller.live.setMode('video-quality');controller.live.setLiveModel('ovda-small-c16')
            controller.live.setStereoLayout('half-tb');controller.live.setPresentationHz(60)
            controller.main_window.show()
            try:app.exec()
            finally:shiboken6.delete(engine)


if __name__=='__main__':main()
