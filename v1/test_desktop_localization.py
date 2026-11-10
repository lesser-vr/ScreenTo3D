"""Rendered bilingual UX and optional live native-session language switching."""
import argparse
import json
import os
from pathlib import Path
import time
from unittest.mock import patch

import shiboken6
from PySide6.QtCore import QObject,QPointF,QSettings,Qt,QMimeData
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from depthsbs_app.desktop import create_app
from depthsbs_app.desktop_preferences import DesktopPreferences
from depthsbs_app.messages import Message as M, ErrorMessage as E


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--native',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    prefs=DesktopPreferences(QSettings(str(args.output/'preferences.ini'),QSettings.IniFormat))
    prefs.store.setValue('ui/language','ko')
    sources=patch('depthsbs_app.live_preview.windows',return_value=[dict(kind='window',id=11,pid=1,
        label='Test video / 한글 테스트',width=1280,height=720)])
    sources.start()
    app,engine,desktop=create_app(prefs)
    live=desktop.live;window=desktop.main_window;language=desktop.language
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
        for code,label in (('ko','SBS 시작'),('en','Start SBS')):
            language.setLanguage(code);pump()
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
        report.update(passed=True,qt_warnings=warnings,error_copy_and_retranslation=True,picker_keyboard_and_persistence=True)
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
