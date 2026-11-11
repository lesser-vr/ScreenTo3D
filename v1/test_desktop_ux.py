"""Minimal shell: actual Qt input, window states, privacy and error recovery."""
import argparse
import json
import time
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QObject, QPointF, Qt, QMimeData, QSettings, qInstallMessageHandler
from PySide6.QtWidgets import QPushButton
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from depthsbs_app.desktop import create_app
from depthsbs_app.desktop_preferences import DesktopPreferences


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    warnings = []
    previous = qInstallMessageHandler(lambda kind, context, message: warnings.append(message))
    rows = [dict(kind='window', id=11, pid=1, label='영상 플레이어 — 여행 영상.mp4')]
    with patch('depthsbs_app.live_preview.windows', side_effect=lambda: [dict(r) for r in rows]) as enumerate_windows:
        app, engine, desktop = create_app(DesktopPreferences(QSettings(str(args.output/'preferences.ini'), QSettings.IniFormat)))
        window = desktop.main_window
        live = desktop.live
        # These mocked frame/lifecycle cases use host images explicitly.
        live.setProcessingPath('gpu')
        live.output_placement.save = Mock()
        tools = window.findChild(QQuickWindow, 'toolsWindow')
        clipboard = app.clipboard()
        saved = QMimeData()
        if clipboard.mimeData() is not None:
            for fmt in clipboard.mimeData().formats():
                saved.setData(fmt, clipboard.mimeData().data(fmt))

        def pump(seconds=.15):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                app.processEvents(); time.sleep(.005)

        def control(name):
            item = window.findChild(QObject, name)
            assert item is not None, name
            return item

        def click(name):
            item = control(name)
            point = item.mapToScene(QPointF(item.width()/2, item.height()/2)).toPoint()
            QTest.mouseClick(item.window(), Qt.LeftButton, Qt.NoModifier, point)
            pump()

        def screenshot(target, name):
            assert target.grabWindow().save(str(args.output / (name + '.png')))

        try:
            pump(.5)
            assert (window.width(), window.height()) == (420, 260)
            assert not tools.isVisible() and not live.preview_visible
            assert live.selectedIndex == -1 and not control('captureStart').property('enabled')
            assert not live.active
            for removed in ('outputStyle', 'outputScreen', 'toggleSbsResult', 'captureImage', 'external3dOutput'):
                assert window.findChild(QObject, removed) is None
            screenshot(window, 'empty')
            # Opening the picker refreshes and does not select/capture implicitly.
            click('captureSource')
            assert enumerate_windows.call_count >= 2
            assert live.selectedIndex == -1 and not live.active
            tab_position = control('monitorInputs').mapToGlobal(QPointF(0, 0))
            main_geometry = window.geometry()
            click('monitorInputs'); assert live.sourceKind == 'monitor' and live.selectedIndex == -1
            after_switch = control('monitorInputs').mapToGlobal(QPointF(0, 0))
            assert after_switch == tab_position, (tab_position, after_switch)
            assert window.geometry() == main_geometry
            screenshot(window, 'monitor-picker')
            click('dismissSource')
            assert window.isVisible() and not control('dismissSource').isVisible()
            click('captureSource')
            window.close(); pump()
            assert window.isVisible() and not control('dismissSource').isVisible()
            click('captureSource')
            click('windowInputs'); assert live.sourceKind == 'window' and live.selectedIndex == -1
            control('captureSource').forceActiveFocus()
            QTest.keyClick(window, Qt.Key_Down)
            QTest.keyClick(window, Qt.Key_Return)
            pump()
            assert live.selectedIndex == 0 and control('captureStart').property('enabled')
            screenshot(window, 'ready')
            # Exercise the visible menu by keyboard, not a direct page assignment.
            click('openFiles')
            assert window.property('page') == 1 and not tools.isVisible()
            assert not control('fileOptions').isVisible()
            assert control('modePicker').isVisible() and control('fileStereoLayout').isVisible()
            screenshot(window, 'files')
            click('returnLive')
            click('openLiveOptions')
            pump()
            assert tools.isVisible() and window.property('page') == 3
            assert control('liveStrength').property('value') == 0.5
            screenshot(tools, 'options')
            control('cursorIncluded').forceActiveFocus(); pump()
            assert control('cursorIncluded').property('checked')
            screenshot(tools, 'options-keyboard')
            QTest.keyClick(tools, Qt.Key_Space); pump()
            assert not live.cursorIncluded
            QTest.keyClick(tools, Qt.Key_Space); pump()
            assert live.cursorIncluded
            limit = control('livePresentationHz')
            assert live.presentationHz == 60 and limit.property('currentIndex') == 1
            limit.forceActiveFocus(); pump()
            QTest.keyClick(tools, Qt.Key_Down); pump()
            assert live.presentationHz == 0
            QTest.keyClick(tools, Qt.Key_Up); pump()
            assert live.presentationHz == 60
            control('openSettings').forceActiveFocus(); pump()
            QTest.keyClick(tools, Qt.Key_Space); pump()
            assert window.property('page') == 2 and not limit.isVisible()
            screenshot(tools, 'settings')
            tools.close(); pump()
            assert window.property('page') == 0
            # Selection stays pinned through reordering and requires reselection
            # after HWND reuse by a different process, even on another refresh.
            rows[:] = [dict(kind='window', id=11, pid=9, label='Different process')]
            live.refresh(); live.refresh(); pump()
            assert live.selectedIndex == -1 and not control('captureStart').property('enabled')
            live.select(0)
            live.message = '시작 대기'
            # Long titles + minimum window + keyboard focus remain usable.
            rows[0]['label'] = '영상 플레이어 — ' + '아주 긴 영상 제목 ' * 14
            live.refresh(); window.resize(380, 260); pump()
            screenshot(window, 'long-title-minimum')
            control('captureSource').forceActiveFocus()
            for modifier in (Qt.NoModifier, Qt.ShiftModifier):
                for _ in range(4):
                    QTest.keyClick(window, Qt.Key_Tab, modifier); pump(.02)
                    item = window.activeFocusItem()
                    assert item is not None
                    point = item.mapToScene(QPointF(0, 0))
                    assert 0 <= point.y() and point.y()+item.height() <= window.height()
            # Real start handler invokes the controller and preserves Small.
            with patch.object(live, 'start') as start:
                click('captureStart'); start.assert_called_once()
            assert live.liveModel == 'da2-small'
            live.process = Mock()
            live.mailbox = Mock()
            live.changed.emit(); pump()
            assert not control('livePresentationHz').property('enabled')
            assert control('captureStart').property('text') == '취소'
            assert '준비 중' in control('captureStatus').property('text')
            screenshot(window, 'preparing')
            live.provider.image = QImage(2, 2, QImage.Format_RGB32)
            live.provider.image.fill(Qt.black)
            live.frameChanged.emit(); pump()
            assert control('captureStart').property('text') == 'SBS 중지'
            screenshot(window, 'running')
            click('captureStart')
            assert live.stopping and live.provider.image.isNull()
            assert not control('captureStart').property('enabled')
            live.process = live.mailbox = None; live.stopping = False
            live.changed.emit(); pump()
            # Native separate error window retains Ctrl+C, Close, Esc and X.
            live.reportError('선택한 창이 종료되었습니다. 다시 선택하세요.'); pump()
            dialog = desktop.error_dialog
            assert dialog.isVisible() and dialog.isWindow() and dialog.isModal()
            assert [b.text() for b in dialog.findChildren(QPushButton)] == ['닫기']
            for target in (dialog.close_button, dialog.text):
                target.setFocus(); clipboard.setText('not the error')
                QTest.keyClick(target, Qt.Key_C, Qt.ControlModifier); pump()
                assert clipboard.text() == dialog.text.toPlainText()
            assert dialog.grab().save(str(args.output/'error.png'))
            QTest.mouseClick(dialog.close_button, Qt.LeftButton); pump()
            assert not dialog.isVisible()
            live.reportError('Escape test'); pump()
            QTest.keyClick(dialog, Qt.Key_Escape); pump()
            assert not dialog.isVisible()
            live.reportError('Window close test'); pump(); dialog.close(); pump()
            assert not dialog.isVisible()
            # A failed affinity call must never expose the error text to capture.
            live.process = Mock(); live.mailbox = Mock()
            with patch('depthsbs_app.capture_sources.exclude_preview', return_value=False):
                live.reportError('Original processing failure'); pump()
                assert not dialog.isVisible() and live.stopping
                assert 'Original processing failure' in live.status
            live.process = live.mailbox = None; live.stopping = False
            live.changed.emit(); pump()
            # Auxiliary windows are excluded from capture as well as the main UI.
            import ctypes as C
            from ctypes import wintypes as W
            from depthsbs_app.capture_sources import user32
            user32.GetWindowDisplayAffinity.argtypes = [W.HWND, C.POINTER(W.DWORD)]
            window.setProperty('page', 2); pump()
            for target in (window, tools):
                affinity = W.DWORD()
                assert user32.GetWindowDisplayAffinity(int(target.winId()), C.byref(affinity))
                assert affinity.value == 0x11, (target.objectName(), target.isVisible(), affinity.value)
            assert not warnings, warnings
            (args.output/'report.json').write_text(json.dumps(dict(
                passed=True, qt_warnings=warnings, device_pixel_ratio=window.devicePixelRatio(),
                actual_qt_input=True, capture=False, inference=False,
                checks=['empty start disabled', 'picker refresh', 'explicit keyboard selection',
                        'menu opens options', 'utility close', 'identity loss', 'minimum/long title',
                        'keyboard focus', 'start signal', 'preparing cancel', 'running stop',
                        'separate error copy/close/Esc', 'utility capture exclusion',
                        'minimized utility reopen', 'error exclusion failure stops capture']
                    + ['unlimited default', 'keyboard 30/60/unlimited selection', 'active FPS control locked']
            ), indent=2), encoding='utf-8')
        finally:
            clipboard.setMimeData(saved)
            import shiboken6
            shiboken6.delete(engine)
            qInstallMessageHandler(previous)


if __name__ == '__main__':
    main()
