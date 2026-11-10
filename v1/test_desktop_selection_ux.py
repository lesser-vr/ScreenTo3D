"""Real Qt activation, hover help and a fresh-process preferences readback."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QPointF, QSettings, Qt
from PySide6.QtTest import QTest
from depthsbs_app.desktop import create_app, DesktopController
from depthsbs_app.desktop_preferences import DesktopPreferences
from depthsbs_app.live_preview import LivePreview
import shiboken6


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    prefs = DesktopPreferences(QSettings(str(args.output/'settings.ini'), QSettings.IniFormat))
    if args.verify:
        from PySide6.QtWidgets import QApplication
        app = QApplication([])
        desktop = DesktopController(prefs)
        live = LivePreview(desktop)
        print(json.dumps(dict(live=[live.liveMode, live.liveModel, live.stereoLayout],
                              file=[desktop.settings[k] for k in ('mode', 'model', 'stereo_layout')],
                              vfg=live.vfgEnabled)))
        return
    args.output.mkdir(parents=True, exist_ok=False)
    with patch('depthsbs_app.live_preview.windows', return_value=[]):
        app, engine, desktop = create_app(prefs)
    root, live = desktop.main_window, desktop.live
    tools = root.findChild(QObject, 'toolsWindow')
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
    results = {}

    def pump(seconds=.15):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(.004)

    def control(name):
        item = root.findChild(QObject, name)
        assert item is not None, name
        return item

    def key(name, key):
        item = control(name)
        item.forceActiveFocus()
        pump()
        QTest.keyClick(item.window(), key)
        pump()

    try:
        assert live.liveMode == 'performance' and live.stereoLayout == 'half-tb'
        root.setProperty('page', 3)
        pump(.3)
        assert control('livePolicy').property('currentIndex') == 0
        assert control('livePolicy').property('currentText') == 'DA2 Small · FP16 · 기본'
        assert root.findChild(QObject, 'liveModel') is None
        assert root.findChild(QObject, 'modelPicker') is None
        model_help = control('liveModelHelp')
        model_help.forceActiveFocus()
        pump(.4)
        assert model_help.findChild(QObject, 'helpPopup').property('visible')
        assert 'FP32' in model_help.property('helpText')
        assert tools.grabWindow().save(str(args.output/'small-model-help.png'))
        model_help.setFocus(False)
        key('livePolicy', Qt.Key_Down)
        assert control('livePolicy').property('currentText') == 'DA2 Base · FP16 혼합'
        key('livePolicy', Qt.Key_Down)
        assert live.liveModel == 'vda-small'
        assert control('livePolicy').property('currentText').startswith('VDA Small · FP')
        assert '시간' in model_help.property('helpText') and 'FP32' in model_help.property('helpText')
        model_help.forceActiveFocus()
        pump(.4)
        assert tools.grabWindow().save(str(args.output/'vda-model-help.png'))
        live.setMode('performance')
        key('livePolicy', Qt.Key_Space)
        assert tools.grabWindow().save(str(args.output/'model-choices.png'))
        QTest.keyClick(tools, Qt.Key_Escape)
        pump()
        assert control('liveStereoLayout').property('currentIndex') == 3
        help_button = control('vfgHelp')
        help_popup = help_button.findChild(QObject, 'helpPopup')
        assert not help_popup.property('visible')
        # Keyboard focus reveals the item in the scroll view; mouse hover alone
        # subsequently opens the popup without activating VFG.
        help_button.forceActiveFocus()
        pump(.4)
        assert help_popup.property('visible')
        help_button.setFocus(False)
        QTest.mouseMove(tools, QPointF(5, 5).toPoint())
        pump(.1)
        assert not help_popup.property('visible')
        point = help_button.mapToScene(QPointF(help_button.width()/2, help_button.height()/2)).toPoint()
        QTest.mouseMove(tools, point)
        pump(.5)
        assert help_popup.property('visible')
        assert 'Ctrl+Alt+S' in help_button.property('helpText')
        assert 'GPU' in help_button.property('helpText')
        assert tools.grabWindow().save(str(args.output/'vfg-hover-help.png'))
        QTest.mouseMove(tools, QPointF(5, 5).toPoint())
        pump(.15)
        assert not help_popup.property('visible')
        live.setMode('video-quality')
        pump()
        assert help_button.property('enabled') and live.vfgUnavailableReason in help_button.property('helpText')
        live.setMode('performance')
        key('livePolicy', Qt.Key_Down)
        assert live.liveMode == 'balanced'
        key('liveStereoLayout', Qt.Key_Up)
        assert live.stereoLayout == 'full-tb'
        root.setProperty('page', 1)
        root.setProperty('fileSettings', True)
        pump()
        key('modePicker', Qt.Key_Down)
        assert desktop.settings['mode'] == 'balanced'
        assert control('modePicker').property('currentText') == 'DA2 Base · FP16 혼합'
        file_help = control('fileModelHelp')
        file_help.forceActiveFocus()
        pump(.4)
        assert 'FP32' in file_help.property('helpText')
        assert root.grabWindow().save(str(args.output/'file-model-help.png'))
        key('fileStereoLayout', Qt.Key_Up)
        assert desktop.settings['stereo_layout'] == 'full-tb'
        # Fresh process reads the INI and constructs new controllers.
        code = "import sys; sys.path.append(" + repr(str(Path(__file__).resolve().parent)) + "); import test_desktop_selection_ux; test_desktop_selection_ux.main()"
        child = subprocess.run([sys.executable, '-c', code, '--output', str(args.output.resolve()), '--verify'],
                               capture_output=True, text=True, timeout=30)
        assert child.returncode == 0, child.stderr
        restored = json.loads(child.stdout)
        assert restored['live'] == ['balanced', 'da2-base', 'full-tb'], restored
        assert restored['file'] == ['balanced', 'da2-base', 'full-tb'], restored
        assert restored['vfg'] is False
        assert not warnings, warnings
        results.update(passed=True, fresh_defaults=['da2-small', 'half-tb'], restored=restored,
                       hover_and_focus_help=True, disabled_vfg_help=True, model_and_precision_help=True,
                       model_choices=live.depthChoices, qt_warnings=warnings)
    finally:
        (args.output/'report.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        shiboken6.delete(engine)


if __name__ == '__main__':
    main()
