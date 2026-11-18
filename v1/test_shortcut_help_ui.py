"""App-owned shortcut-help UI regression; no capture, inference or global input."""
import argparse,json,time
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QObject,QPoint,QPointF,QSettings,Qt,QMetaObject
from PySide6.QtTest import QTest
from screento3d_app.desktop import create_app
from screento3d_app.desktop_preferences import DesktopPreferences
import shiboken6

class RegisteredVfg:
    registered=True
    def __init__(self,*_):pass
    def close(self,*_):pass

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    with patch('screento3d_app.vfg_hotkey.VfgHotkey',RegisteredVfg):
        app,engine,c=create_app(DesktopPreferences(QSettings(str(args.output/'preferences.ini'),QSettings.IniFormat)))
    main=c.main_window;guide=main.findChild(QObject,'mainShortcutGuide')
    errors=[];engine.warnings.connect(lambda values:errors.extend(str(v.toString()) for v in values))
    report=dict(passed=False,cases=[],scope='Actual owned QML windows, synthetic Qt mouse/keyboard, fake VFG registration; no capture or inference')
    def pump(seconds=.15):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:app.processEvents();time.sleep(.003)
    def click(window,item):
        point=item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint()
        QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,point);pump()
    def button(name):
        return next(i for i in main.findChildren(QObject,name) if i.isVisible())
    def visual_item(item,name):
        if item.objectName()==name:return item
        for child in item.childItems():
            found=visual_item(child,name)
            if found is not None:return found
        return None
    def snapshot(window,name):
        image=window.grabWindow();assert not image.isNull();assert image.save(str(args.output/name))
    try:
        pump(.4)
        for language in ('ko','en'):
            c.language.setLanguage(language);pump()
            for width,height in ((380,260),(420,260)):
                main.resize(width,height);pump()
                opener=button('openShortcutGuide');click(main,opener)
                assert guide.property('visible')
                scroll=guide.findChild(QObject,'shortcutGuideScroll')
                assert scroll.property('contentItem').property('contentY')==0
                assert (main.width(),main.height())==(width,height)
                assert guide.property('x')>=0 and guide.property('y')>=0
                assert guide.property('x')+guide.property('width')<=width
                assert guide.property('y')+guide.property('height')<=height
                snapshot(main,f'{language}-{width}x{height}.png')
                scroll=guide.findChild(QObject,'shortcutGuideScroll')
                content=scroll.property('contentItem')
                assert content.property('contentHeight')>content.property('height')
                header=guide.findChild(QObject,'shortcutGuideHeader')
                header_position=header.mapToScene(QPointF())
                content.setProperty('contentY',content.property('contentHeight')-content.property('height'));pump()
                assert header.mapToScene(QPointF())==header_position
                snapshot(main,f'{language}-{width}x{height}-bottom.png')
                QTest.keyClick(main,Qt.Key_Escape);pump();assert not guide.property('visible')
                assert opener.hasActiveFocus()
                QTest.keyClick(main,Qt.Key_Space);pump();assert guide.property('visible')
                QTest.mouseClick(main,Qt.LeftButton,Qt.NoModifier,QPoint(2,2));pump()
                assert not guide.property('visible')
                report['cases'].append(dict(language=language,width=width,height=height,bounded=True,scrollable=True,keyboard_open_close=True))
        c.language.setLanguage('ko');main.setProperty('page',3);pump()
        tools=main.findChild(QObject,'toolsWindow');settingsGuide=main.findChild(QObject,'settingsShortcutGuide')
        entry=main.findChild(QObject,'openSettingsShortcutGuide')
        assert tools.isVisible();click(tools,entry)
        assert settingsGuide.property('visible')
        snapshot(tools,'ko-settings.png')
        QMetaObject.invokeMethod(settingsGuide,'close');pump()
        report['cases'].append(dict(settings_entry=True))
        # Render a deterministic conflict without reserving anyone else's keys.
        from tests.test_shortcut_help import Live
        real_live=c.shortcut_help.live
        fake=Live();fake.active=True;fake.output_policy.state=True
        c.shortcut_help.live=fake;c.shortcut_help.vfg_hotkey.registered=False
        c.shortcut_help.refresh();pump()
        click(tools,entry);assert settingsGuide.property('visible')
        snapshot(tools,'ko-conflicting-shortcuts.png')
        fallback=visual_item(settingsGuide.property('contentItem'),'shortcutFallback_fullscreen')
        assert fallback.isVisible() and fallback.isEnabled()
        click(tools,fallback);fake.toggleOutputFullscreen.assert_called_once()
        QMetaObject.invokeMethod(settingsGuide,'close');pump()
        c.shortcut_help.live=real_live;c.shortcut_help.refresh()
        report['cases'].append(dict(conflict_fallback=True))
        assert not errors,errors
        report['passed']=True
    finally:
        main.close();app.processEvents();shiboken6.delete(engine)
        (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
if __name__=='__main__':main()
