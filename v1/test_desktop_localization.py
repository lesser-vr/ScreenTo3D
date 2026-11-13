"""Rendered bilingual UX and optional live native-session language switching."""
import argparse
import json
import os
from pathlib import Path
import time
from unittest.mock import patch,Mock

import shiboken6
from PySide6.QtCore import QObject,QPointF,QSettings,Qt,QMimeData
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from screento3d_app.desktop import create_app
from screento3d_app.desktop_preferences import DesktopPreferences
from screento3d_app.messages import Message as M, ErrorMessage as E


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--native',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    prefs=DesktopPreferences(QSettings(str(args.output/'preferences.ini'),QSettings.IniFormat))
    prefs.store.setValue('ui/language','ko')
    sources=patch('screento3d_app.live_preview.windows',return_value=[dict(kind='window',id=11,pid=1,
        label='Test video / 한글 테스트',width=1280,height=720)])
    sources.start()
    app,engine,desktop=create_app(prefs)
    live=desktop.live;window=desktop.main_window;language=desktop.language
    forbidden_shutdown=Mock(side_effect=AssertionError('OS shutdown is forbidden in GUI tests'))
    desktop.shutdown.command=forbidden_shutdown
    live.output_placement.save=lambda:None
    live.output_placement.path=args.output/'placement.json'
    warnings=[];engine.warnings.connect(lambda errors:warnings.extend(e.toString() for e in errors))
    tools=window.findChild(QQuickWindow,'toolsWindow')
    report=dict(passed=False,dpi=window.devicePixelRatio(),captures=[],native=None)
    clipboard=app.clipboard();saved=QMimeData()
    if clipboard.mimeData() is not None:
        for fmt in clipboard.mimeData().formats():saved.setData(fmt,clipboard.mimeData().data(fmt))
    oracle=None

    def pump(seconds=.12):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            app.processEvents();time.sleep(.003)

    def control(name):
        item=window.findChild(QObject,name)
        assert item is not None,name
        return item

    def capture(target,name):
        pump();assert target.grabWindow().save(str(args.output/(name+'.png')))
        report['captures'].append(name)

    def wait(predicate,timeout=50):
        end=time.monotonic()+timeout
        while time.monotonic()<end and not predicate():pump(.03)
        assert predicate(),live.status

    try:
        window.resize(380,260)
        for code,label in (('ko','3D 시작'),('en','Start 3D')):
            language.setLanguage(code);pump()
            assert control('liveTab').property('text')==('실시간 3D' if code=='ko' else 'Live 3D')
            assert control('captureStart').property('text')==label
            assert control('captureStart').property('width')>=control('captureStart').property('implicitWidth')
            capture(window,code+'-live-minimum')
            # Actual pointer input opens the translated monitor/window tabs.
            source=control('captureSource');point=source.mapToScene(QPointF(source.width()/2,source.height()/2))
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,point.toPoint());pump()
            tab=control('windowInputs')
            assert tab.width()>=tab.implicitWidth()
            capture(window,code+'-source-picker')
            QTest.keyClick(window,Qt.Key_Escape);pump()
            window.setProperty('page',3);pump()
            capture(tools,code+'-live-settings')
            window.setProperty('page',2);pump()
            assert control('languagePicker').property('currentValue')==code
            capture(tools,code+'-language-settings')
            window.setProperty('page',1);pump()
            window.resize(760,620)
            capture(window,code+'-file-workspace')
            # Hover the unused right side of the real output label with no file.
            path_label=control('fileOutputPath');path_label.forceActiveFocus();pump()
            tooltip=next(child for child in path_label.children() if child.inherits('QQuickToolTipAttached'))
            point=path_label.mapToScene(QPointF(path_label.width()-5,path_label.height()/2))
            QTest.mouseMove(window,point.toPoint());pump(.6)
            assert not desktop.destination and not tooltip.property('visible')
            capture(window,code+'-empty-output-hover')
            source=args.output/'tooltip-generated-video.mp4';source.touch(exist_ok=True)
            desktop.add_paths([str(source)])
            control('modePicker').forceActiveFocus();path_label.forceActiveFocus();pump()
            point=path_label.mapToScene(QPointF(path_label.width()-5,path_label.height()/2))
            QTest.mouseMove(window,point.toPoint());pump(.7)
            assert tooltip.property('visible') and tooltip.property('text')==desktop.destination
            capture(window,code+'-output-path-tooltip')
            destination=desktop.destination
            desktop.rows[0]['output']='   ';desktop.changed.emit();pump()
            assert not tooltip.property('visible')
            desktop.rows[0]['output']=destination;desktop.changed.emit();pump()
            assert tooltip.property('visible')
            desktop.removeSelected();pump()
            assert not desktop.destination and not tooltip.property('visible')
            QTest.mouseMove(window,QPointF(2,2).toPoint());pump()
            assert not control('fileOptions').isVisible()
            assert control('modePicker').isVisible() and control('fileStereoLayout').isVisible()
            file_strength=control('fileStrength');file_strength.forceActiveFocus();pump()
            assert file_strength.property('value')==.5 and not desktop.settings['vfg']
            QTest.keyClick(window,Qt.Key_Right);pump()
            assert desktop.settings['depth_strength']==.75 and live.depthStrength==.5
            file_vfg=control('fileVfg');file_vfg.forceActiveFocus();QTest.keyClick(window,Qt.Key_Space);pump()
            assert desktop.settings['vfg'] and not live.vfgEnabled
            control('fileVfgHelp').forceActiveFocus();pump(.4)
            capture(window,code+'-file-depth-vfg')
            file_vfg.forceActiveFocus();QTest.keyClick(window,Qt.Key_Space);pump()
            assert not desktop.settings['vfg']
            control('resetFileStrength').forceActiveFocus();QTest.keyClick(window,Qt.Key_Space);pump()
            assert desktop.settings['depth_strength']==.5
            desktop.lease.acquire('file');desktop.changed.emit();pump()
            assert not file_vfg.property('enabled') and not file_strength.property('enabled')
            desktop.lease.release('file');desktop.changed.emit();pump()
            checkbox=control('fileLetterboxRefinement');help_button=control('fileLetterboxHelp')
            assert checkbox.property('text')==('검은 여백 영상의 단색 배경 깊이 보정' if code=='ko'
                else 'Uniform-background depth refinement for videos with black bars')
            assert not checkbox.property('checked') and not desktop.settings['letterbox']
            help_button.forceActiveFocus();pump(.5)
            popup=help_button.findChild(QObject,'helpPopup')
            assert popup is not None and popup.property('visible')
            assert ('기본 꺼짐' if code=='ko' else 'Default: off') in help_button.property('helpText')
            # Move focus away, then open the same overlay by actual mouse hover.
            checkbox.forceActiveFocus();QTest.mouseMove(window,QPointF(2,2).toPoint());pump(.4)
            assert not popup.property('visible')
            point=help_button.mapToScene(QPointF(help_button.width()/2,help_button.height()/2))
            QTest.mouseMove(window,point.toPoint());pump(.5)
            assert help_button.property('hovered') and popup.property('visible')
            capture(window,code+'-black-bar-help')
            QTest.mouseMove(window,QPointF(2,2).toPoint());pump(.4)
            assert not popup.property('visible')
            checkbox.forceActiveFocus();QTest.keyClick(window,Qt.Key_Space);pump()
            assert checkbox.property('checked') and desktop.settings['letterbox']
            QTest.keyClick(window,Qt.Key_Space);pump()
            assert not checkbox.property('checked') and not desktop.settings['letterbox']
            power=control('shutdownAfterConversion');power.forceActiveFocus();pump()
            assert not power.property('checked') and not desktop.shutdown.selected
            QTest.keyClick(window,Qt.Key_Space);pump()
            assert desktop.shutdown.selected
            desktop.shutdown.begin();pump()
            assert control('cancelShutdown').isVisible() and window.property('page')==1
            capture(window,code+'-shutdown-countdown')
            cancel=control('cancelShutdown');point=cancel.mapToScene(QPointF(cancel.width()/2,cancel.height()/2))
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,point.toPoint());pump()
            assert not desktop.shutdown.pending and not desktop.shutdown.selected
            window.setProperty('page',0);pump()

        live.selectDepthModel('video-quality/ovda-small-c16')
        window.setProperty('page',3);pump()
        consent=control('ovdaConsent')
        assert consent.width()<=tools.width()-40
        assert consent.height()>=30
        capture(tools,'en-long-license-label')
        tools.resize(460,430);pump()
        original_label=consent.property('text');original_height=consent.height()
        consent.setProperty('text',original_label+' '+original_label);pump()
        assert consent.height()>original_height
        assert consent.width()<=tools.width()-40
        capture(tools,'en-expanded-label-wrap')
        consent.setProperty('text',original_label)
        report['expanded_label_wrap']=True
        live.setMode('performance');window.setProperty('page',0);pump()

        # The picker itself saves the language via keyboard input.
        window.setProperty('page',2);pump()
        picker=control('languagePicker');picker.forceActiveFocus()
        QTest.keyClick(tools,Qt.Key_Up);pump()
        assert language.selected=='ko' and prefs.store.value('ui/language')=='ko'
        window.setProperty('page',0);pump()

        error=desktop.error_dialog
        original='opaque diagnostic CODE-17 / 한글'
        error.showError(E('E_OUTPUT_FRAME_DELIVERY',v0=original,details='driver result CODE-17'))
        language.setLanguage('en');pump()
        assert 'Direct GPU frame delivery failed:' in error.text.toPlainText()
        assert 'Error ID: E_OUTPUT_FRAME_DELIVERY' in error.text.toPlainText()
        assert 'Details:\ndriver result CODE-17' in error.text.toPlainText()
        assert original in error.text.toPlainText(),error.text.toPlainText()
        assert 'Close' in error.close_button.text().replace('&',''),error.close_button.text()
        QTest.keyClick(error.text,Qt.Key_C,Qt.ControlModifier);pump()
        assert clipboard.text()==error.text.toPlainText()
        language.setLanguage('ko');pump()
        assert 'GPU 직접 프레임 전달 실패:' in error.text.toPlainText()
        assert '오류 ID: E_OUTPUT_FRAME_DELIVERY' in error.text.toPlainText()
        assert original in error.text.toPlainText(),error.text.toPlainText()
        assert '닫기' in error.close_button.text(),error.close_button.text()
        assert error.grab().save(str(args.output/'ko-error.png'))
        error.reject()

        # Language changes update an existing notice without restarting its timer.
        output=live.output_window;output.resize(960,540);output.showNormal();pump()
        notice=control('vfgNotice')
        for layout in ('full-sbs','half-sbs','full-tb','half-tb'):
            live.setStereoLayout(layout)
            live.notifyVfg(M('Preparing VFG…'),True);pump()
            for code,text in (('en','Preparing VFG…'),('ko','VFG 준비 중…')):
                language.setLanguage(code);pump()
                assert notice.property('message')==text
                assert notice.property('pending') and notice.opacity()==1
            capture(output,layout+'-ko-notice')
        live.notifyVfg('VFG ON',False);pump(.85)
        language.setLanguage('en');pump(1.05)
        assert notice.opacity()==0 and notice.property('message')==''
        report['notice_timer_not_restarted']=True
        output.hide()

        if args.native:
            from benchmark_live_modes import ClockOracle
            oracle=ClockOracle('generated');oracle.resize(640,360);oracle.show();pump(.3)
            live.items=[dict(kind='window',id=int(oracle.winId()),pid=os.getpid(),label=oracle.windowTitle(),
                             width=round(oracle.width()*oracle.devicePixelRatioF()),height=round(oracle.height()*oracle.devicePixelRatioF()))]
            live.selected=0;live.setMode('performance');live.setStereoLayout('half-tb');live.setPresentationHz(60)
            live.startSbs(0,0)
            wait(lambda: live.active and live.native is not None and live.native.report()['output']['submitted_frames']>=5)
            identity=(live.process.pid,live.session,dict(live.source),live.output_window,live.stereo_layout,live.live_model)
            transitions=[]
            for code in ('ko','en','ko','en'):
                before=live.native.report()['output']['submitted_frames']
                language.setLanguage(code)
                wait(lambda: live.active and live.native.report()['output']['submitted_frames']>before+5,15)
                assert identity==(live.process.pid,live.session,dict(live.source),live.output_window,live.stereo_layout,live.live_model)
                assert desktop.lease.owner=='live'
                transitions.append(dict(language=code,pid=live.process.pid,session=live.session,frames=live.native.report()['output']['submitted_frames']))
            capture(output,'native-en-output')
            report['native']=dict(passed=True,transitions=transitions,capture='owned generated window only',model=live.live_model,layout=live.stereo_layout)
            live.stop();wait(lambda:not live.active,15)
            assert desktop.lease.owner is None and live.native.report()['live_pools']==0
        assert not warnings,warnings
        forbidden_shutdown.assert_not_called()
        report.update(passed=True,qt_warnings=warnings,error_copy_and_retranslation=True,picker_keyboard_and_persistence=True,
                      black_bar_help_hover_and_focus=True,black_bar_checkbox_binding=True,empty_path_tooltip_suppressed=True,
                      file_strength_and_vfg_binding=True,file_controls_busy_lock=True)
    finally:
        if live.active:
            live.stop()
            until=time.monotonic()+15
            while live.active and time.monotonic()<until:pump(.03)
        if oracle is not None:oracle.close()
        clipboard.setMimeData(saved)
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        language.close();shiboken6.delete(engine);sources.stop()


if __name__=='__main__':main()
