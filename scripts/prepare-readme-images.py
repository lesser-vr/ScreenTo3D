"""Prepare documentation media from an existing, attributed Spring subset.

Run with the prepared local GPU/Qt environment; never downloads model artifacts.
The example uses the ordinary live policy, not camera-calibrated benchmark output.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import os
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'v1'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_example(args):
    import cv2
    import numpy as np
    import torch
    from evaluate_sbs_quality import open_session,Session
    from depthsbs_app.desktop_jobs import BUNDLE
    from depthsbs_app.resources import configure_resource_root
    from depthsbs_app.stereo_layout import dimensions

    source=args.source/'spring/train/0001/frame_left'
    assert args.frames>=32,'Use enough ordinary temporal updates before capture.'
    paths=[source/f'frame_left_{i:04d}.png' for i in range(1,args.frames+1)]
    if not all(p.is_file() for p in paths):raise FileNotFoundError('Prepare the existing Spring 0001 left-camera subset first.')
    args.output.mkdir(parents=True,exist_ok=True)
    configure_resource_root(BUNDLE);cv2.setNumThreads(1)
    first=cv2.imread(str(paths[0]));height,width=first.shape[:2]
    assert (width,height)==(1920,1080),'Keep the dataset RGB sampling unchanged.'
    with ExitStack() as stack:
        backend,owner,post,policy=open_session(stack,'da2-small',width,height,'half-tb',False)
        session=Session(backend,owner,post,policy,'da2-small')
        resets=[]
        for index,path in enumerate(paths):
            bgr=cv2.imread(str(path))
            if bgr is None or bgr.shape!=first.shape:raise ValueError('Unexpected Spring frame shape')
            rgb=np.ascontiguousarray(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
            packed,_,reason=session.frame(rgb,index)
            if reason:resets.append(dict(frame=index+1,reason=reason))
        assert packed.shape==(height,width,4)
        assert dimensions(width,height,'half-tb')==(width,height)
        packed_bgr=cv2.cvtColor(packed,cv2.COLOR_RGBA2BGR)
        # Native texture readback is RGBA, including both packed eyes. No crop,
        # calibration, unpack/restore, overlay or synthetic second eye is added.
        eye_delta=float(np.abs(packed_bgr[:height//2].astype(np.int16)-packed_bgr[height//2:].astype(np.int16)).mean())
        assert eye_delta>.05,'Reject a duplicated-mono example.'
        source_png=args.output/'spring-original.png';packed_png=args.output/'spring-half-tb.png'
        assert cv2.imwrite(str(source_png),bgr,[cv2.IMWRITE_PNG_COMPRESSION,9])
        assert cv2.imwrite(str(packed_png),packed_bgr,[cv2.IMWRITE_PNG_COMPRESSION,9])
        for name,pixels in (('spring-original-preview.webp',bgr),('spring-half-tb-preview.webp',packed_bgr)):
            preview=cv2.resize(pixels,(960,540),interpolation=cv2.INTER_AREA)
            assert cv2.imwrite(str(args.output/name),preview,[cv2.IMWRITE_WEBP_QUALITY,88])
        decoded=cv2.imread(str(packed_png))
        assert np.array_equal(decoded,packed_bgr),'PNG must preserve the native packed bytes.'
        source_identity=dict(file=f'spring/train/0001/frame_left/{paths[-1].name}',sha256=digest(paths[-1]))
    report=dict(
        source=dict(dataset='Spring',version=2,doi='10.18419/DARUS-3376',
            url='https://doi.org/10.18419/DARUS-3376',license='CC-BY-4.0',
            creators=['Lukas Mehl','Jenny Schmalfuss','Azin Jahedi','Yaroslava Nalivayko','Andrés Bruhn'],
            film_assets='Spring, Blender Foundation / Blender Studio, CC-BY-4.0',**source_identity),
        processing=dict(model='DA2 Small',precision='FP16',strength=.5,vfg=False,
            renderer='native CUDA live Half Top-and-Bottom',input_size=[width,height],
            output_size=[width,height],packed_eye_size=[width,height//2],
            eye_order='left eye above right eye',frames=args.frames,source_clock_hz=60,
            camera_calibration=False,default_comfort_policy=True,resets=resets,
            changes='Native stereo synthesis; unchanged source RGB PNG re-encoding; 960x540 lossy web previews.'),
        verification=dict(native_png_roundtrip_exact=True,eyes_mean_absolute_difference=eye_delta,
            gpu=torch.cuda.get_device_name(),revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            scope='A documented still example, not FPS, quality ranking or display-comfort validation.'),
        files={p.name:dict(bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(args.output.iterdir()) if p.suffix in ('.png','.webp')})
    (args.output/'example.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)


def capture_ui(args):
    """Capture the production shell with owned public input, never the desktop."""
    from unittest.mock import patch,Mock
    from PySide6.QtCore import QObject,QSettings,QTimer,Qt,QPointF,QRect
    from PySide6.QtGui import QImage,QPainter
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QWidget
    from depthsbs_app.desktop import create_app
    from depthsbs_app.desktop_preferences import DesktopPreferences
    from depthsbs_app.output_placement import OutputPlacement
    from depthsbs_app.desktop_jobs import BUNDLE

    scratch=ROOT/'out/readme-capture-20261111';scratch.mkdir(exist_ok=True)
    args.output.mkdir(parents=True,exist_ok=True)
    prefs=DesktopPreferences(QSettings(str(scratch/'preferences.ini'),QSettings.IniFormat))
    prefs.store.clear();prefs.store.setValue('ui/language','en')
    owned=[]
    with patch('depthsbs_app.live_preview.windows',side_effect=lambda:list(owned)):
        app,engine,desktop=create_app(prefs)
        live=desktop.live;window=desktop.main_window;language=desktop.language
        desktop.shutdown.command=Mock(side_effect=AssertionError('Documentation capture cannot shut down Windows'))
        live.output_placement=OutputPlacement(scratch/'placement-unused.json')
        live.output_placement.rect=QRect(150,80,960,540)
        live.output_placement.save=lambda:None
        warnings=[];engine.warnings.connect(lambda errors:warnings.extend(e.toString() for e in errors))
        def pump(seconds=.12):
            end=time.monotonic()+seconds
            while time.monotonic()<end:app.processEvents();time.sleep(.004)
        def wait(predicate,seconds=45):
            end=time.monotonic()+seconds
            while not predicate() and time.monotonic()<end:pump(.04)
            assert predicate(),str(live.status)
        def control(name):
            result=window.findChild(QObject,name)
            assert result is not None,name
            return result
        def save(name):
            pump(.3);path=args.output/name
            image=window.grabWindow()
            assert not image.isNull() and image.save(str(path))
            return dict(width=image.width(),height=image.height(),bytes=path.stat().st_size,sha256=digest(path))

        class SpringPlayer(QWidget):
            def __init__(self):
                super().__init__();self.setWindowTitle('Spring · CC BY 4.0')
                self.images=[QImage(str(args.source/f'spring/train/0001/frame_left/frame_left_{i:04d}.png')) for i in range(1,65)]
                assert all(not image.isNull() for image in self.images)
                self.frame=0;self.resize(960,540);self.move(600,300)
                self.timer=QTimer(self);self.timer.timeout.connect(self.advance);self.timer.start(33)
            def advance(self):self.frame=(self.frame+1)%len(self.images);self.update()
            def paintEvent(self,event):
                painter=QPainter(self);painter.drawImage(self.rect(),self.images[self.frame]);painter.end()

        player=SpringPlayer();player.show();pump(.4)
        owned.append(dict(kind='window',id=int(player.winId()),pid=os.getpid(),label=player.windowTitle(),
            width=round(player.width()*player.devicePixelRatioF()),height=round(player.height()*player.devicePixelRatioF())))
        files={};proof={}
        try:
            live.refresh();live.select(0)
            assert live.live_model=='da2-small' and live.depthStrength==.5 and not live.vfgEnabled
            live.setProcessingPath('gpu-texture');live.setPresentationHz(60)
            window.setPosition(40,40);window.resize(420,260);window.showNormal();pump()
            button=control('captureStart');point=button.mapToScene(QPointF(button.width()/2,button.height()/2))
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,point.toPoint())
            wait(lambda:live.active and live.hasFrame and live.native is not None and live.native.report()['output']['submitted_frames']>=12)
            proof=dict(native_session=True,submitted_frames=live.native.report()['output']['submitted_frames'],
                source='Owned Spring player window only',model=live.live_model,strength=live.depthStrength,vfg=live.vfgEnabled)
            for code,label in (('en','Stop 3D'),('ko','3D 중지')):
                language.setLanguage(code);pump()
                assert control('captureStart').property('text')==label
                assert control('liveTab').property('text')==('Live 3D' if code=='en' else '실시간 3D')
                folder=args.output/code;folder.mkdir(exist_ok=True)
                files[f'{code}/ui-live.png']=save(f'{code}/ui-live.png')
            live.stop();wait(lambda:not live.active,20)
            assert desktop.lease.owner is None
            player.timer.stop();player.hide()
            # Real readable example clips populate the queue, without converting
            # or pretending a queue entry completed. No private path is shown.
            media=scratch/'Spring-0001.mp4'
            if not media.is_file():
                sp_args=[str(BUNDLE/'ffmpeg/ffmpeg.exe'),'-v','error','-y','-loop','1','-i',str(args.output/'spring-original.png'),
                    '-t','2','-r','30','-c:v','libx264','-pix_fmt','yuv420p',str(media)]
                subprocess.run(sp_args,check=True,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
            desktop.add_paths([str(media)])
            desktop.rows[0]['output']='Spring-0001_Half_TB.mp4'
            desktop.rows[0]['auto_output']=False
            desktop.changed.emit()
            assert desktop.settings['model']=='da2-base' and desktop.settings['depth_strength']==.5 and not desktop.settings['vfg']
            window.setProperty('page',1);pump();window.resize(860,1100);pump()
            for code in ('en','ko'):
                language.setLanguage(code);window.contentItem().forceActiveFocus();pump()
                # Ensure the published view includes the previously clipped
                # strength/VFG and completion-shutdown controls.
                for name in ('fileStrength','fileVfg','shutdownAfterConversion'):
                    item=control(name);top=item.mapToScene(QPointF(0,0)).y()
                    assert item.isVisible() and 0<=top<window.height()-100,(name,top,window.height())
                files[f'{code}/ui-files.png']=save(f'{code}/ui-files.png')
            desktop.shutdown.command.assert_not_called()
            assert not warnings,warnings
            report=dict(captured='2026-11-11',revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                live=proof,file=dict(model='da2-base',strength=.5,vfg=False,state='queued',
                    output_path='Public relative example destination, to omit local user directories'),
                dpi=window.devicePixelRatio(),files=files,qml_warnings=warnings)
            (args.output/'ui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(report,ensure_ascii=False),flush=True)
        finally:
            if live.active:live.stop();wait(lambda:not live.active,20)
            player.timer.stop();player.close();desktop.shutdown.cancel()
            window.setProperty('page',0);window.close();pump()
            import shiboken6
            language.close();shiboken6.delete(engine)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'out/spring-source')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/images')
    parser.add_argument('--frames',type=int,default=64)
    parser.add_argument('--ui',action='store_true',help='Capture bilingual production UI after preparing the example')
    args=parser.parse_args()
    if args.ui:capture_ui(args)
    else:prepare_example(args)


if __name__=='__main__':main()
