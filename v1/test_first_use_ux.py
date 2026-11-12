"""Rendered first-use guidance regression; no network, model execution or capture."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import time
from unittest.mock import patch

from PySide6.QtCore import QObject,QMetaObject,QSettings,Qt
from PySide6.QtQuick import QQuickWindow

from depthsbs_app.desktop import create_app
from depthsbs_app.desktop_preferences import DesktopPreferences


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    report=dict(passed=False,scope=__doc__,captures=[])
    prefs=DesktopPreferences(QSettings(str(args.output/'preferences.ini'),QSettings.IniFormat))
    prefs.store.setValue('ui/language','ko')
    source=dict(kind='window',id=11,pid=1,label='Owned first-use fixture',width=1280,height=720)
    with ExitStack() as stack:
        stack.enter_context(patch('depthsbs_app.live_preview.windows',return_value=[source]))
        app,engine,desktop=create_app(prefs)
        window=desktop.main_window;live=desktop.live;downloads=desktop.downloads
        setup=window.findChild(QQuickWindow,'runtimeSetupWindow')
        missing={'trt-core'}
        stack.enter_context(patch.object(downloads,'needed',side_effect=lambda key:key in missing))
        stack.enter_context(patch('depthsbs_app.model_downloads.source_for',side_effect=FileNotFoundError('No configured origin')))
        stack.enter_context(patch('depthsbs_app.model_downloads.QStandardPaths.writableLocation',return_value=str(args.output/'downloads')))
        opened=stack.enter_context(patch('depthsbs_app.model_downloads.QDesktopServices.openUrl',return_value=True))
        warnings=[];engine.warnings.connect(lambda errors:warnings.extend(e.toString() for e in errors))
        errors=[];live.errorOccurred.connect(errors.append)

        def pump():
            until=time.monotonic()+.15
            while time.monotonic()<until:app.processEvents();time.sleep(.003)

        def click(parent,name):
            control=parent.findChild(QObject,name);assert control is not None,name
            assert control.property('enabled'),name
            assert QMetaObject.invokeMethod(control,'clicked',Qt.DirectConnection)
            pump()

        def capture(name):
            pump();assert setup.grabWindow().save(str(args.output/(name+'.png')))
            report['captures'].append(dict(name=name,width=setup.width(),height=setup.height()))
            assert not errors and not desktop.error_dialog.isVisible()
            assert not live.active and not desktop.busy

        try:
            live.refresh();live.select(0);desktop.changed.emit();pump()
            click(window,'captureStart')
            assert setup.isVisible() and downloads.setupKey=='trt-core'
            assert downloads.willResume
            capture('ko-required-download')
            setup.resize(380,420);pump();capture('ko-required-download-narrow')
            desktop.language.setLanguage('en');pump();capture('en-required-download-narrow')
            click(setup,'installPrimaryAction')
            assert opened.call_count==1 and downloads.waitingKey=='trt-core'
            capture('en-browser-wait-narrow')
            click(setup,'closeRuntimeSetup')
            assert not downloads.setupVisible and not downloads.waitingKey and downloads.resume is None
            # File Start must remain actionable even when the default Base model is missing.
            missing.clear();missing.add('da2-base')
            path=args.output/'owned-input.mp4';path.touch();desktop.add_paths([str(path)])
            window.setProperty('page',1);window.resize(760,620);desktop.changed.emit();pump()
            click(window,'convertButton')
            assert setup.isVisible() and downloads.setupKey=='da2-base'
            desktop.language.setLanguage('ko');setup.resize(520,420);pump();capture('ko-required-file-model')
            assert not warnings,warnings
            report.update(passed=True,browser_url=opened.call_args.args[0].toString(),errors=len(errors),warnings=warnings)
        finally:
            downloads.dismissSetup();desktop.shutdown.cancel();window.close();pump()
            (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':main()
