"""Render production tooltip owners; no media, user settings or OS commands."""
from pathlib import Path
import os
import tempfile
import unittest
import shiboken6
import PySide6
from PySide6.QtCore import QObject,QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtQuickControls2 import QQuickStyle

_dll_directory=os.add_dll_directory(str(Path(PySide6.__file__).parent)) if os.name=='nt' else None


class TooltipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        QQuickStyle.setStyle('Basic')

    def setUp(self):
        self.engine=QQmlApplicationEngine()
        source='''import QtQuick
import QtQuick.Controls
import "../screento3d_app/qml" as UI
ApplicationWindow {
    width: 760; height: 380; visible: true
    UI.HelpButton { objectName: "sampleHelp"; x: 30; y: 30; helpText: "Help with actual content" }
    UI.ChoicePicker { objectName: "samplePicker"; x: 30; y: 110; width: 150; model: ["A very long translated option that needs a tooltip"] }
    UI.TaskHeader { objectName: "sampleHeader"; x: 30; y: 230; width: 680 }
}'''
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        source=source.replace('../screento3d_app/qml',(Path(__file__).resolve().parents[1]/'screento3d_app/qml').as_uri())
        fixture=Path(self.temp.name)/'fixture.qml';fixture.write_text(source,encoding='utf-8')
        self.engine.load(QUrl.fromLocalFile(str(fixture)))
        QTest.qWait(100)
        self.assertTrue(self.engine.rootObjects())
        self.window=self.engine.rootObjects()[0]
        self.window.requestActivate()
        self.help=self.window.findChild(QObject,'sampleHelp')
        self.picker=self.window.findChild(QObject,'samplePicker')
        self.header=self.window.findChild(QObject,'sampleHeader')
        QTest.qWait(80)

    def tearDown(self):
        self.window.close();shiboken6.delete(self.engine)

    def attached(self,item):
        return next(child for child in item.children() if child.inherits('QQuickToolTipAttached'))

    def focus(self,item):item.forceActiveFocus();QTest.qWait(600)

    def test_help_closes_for_empty_or_whitespace_and_recovers(self):
        popup=self.help.findChild(QObject,'helpPopup')
        self.focus(self.help);self.assertTrue(popup.property('visible'))
        for text in ('',' \t\n '):
            self.help.setProperty('helpText',text);QTest.qWait(20)
            self.assertFalse(popup.property('visible'))
        self.help.setProperty('helpText','Real help');QTest.qWait(400)
        self.assertTrue(popup.property('visible'));self.assertEqual(popup.property('text'),'Real help')

    def test_help_hidden_or_disabled_owner_cannot_show_popup(self):
        popup=self.help.findChild(QObject,'helpPopup');self.focus(self.help)
        self.help.setProperty('visible',False);QTest.qWait(20)
        self.assertFalse(popup.property('visible'))
        self.help.setProperty('visible',True);self.focus(self.help)
        self.assertTrue(popup.property('visible'))
        self.help.setProperty('enabled',False);QTest.qWait(20)
        self.assertFalse(popup.property('visible'))

    def test_picker_blank_clipped_text_never_shows_empty_tooltip(self):
        tooltip=self.attached(self.picker);self.focus(self.picker)
        self.assertTrue(tooltip.property('visible'))
        for text in ('',' '*1000):
            self.picker.setProperty('displayText',text);QTest.qWait(20)
            self.assertFalse(tooltip.property('visible'))
        self.picker.setProperty('displayText','A long useful value '*20);QTest.qWait(600)
        self.assertTrue(tooltip.property('visible'))

    def test_picker_short_value_or_disabled_owner_has_no_tooltip(self):
        tooltip=self.attached(self.picker);self.focus(self.picker)
        self.assertTrue(tooltip.property('visible'))
        self.picker.setProperty('displayText','Short');QTest.qWait(20)
        self.assertFalse(tooltip.property('visible'))
        self.picker.setProperty('displayText','Long '*100);self.picker.setProperty('enabled',False);QTest.qWait(20)
        self.assertFalse(tooltip.property('visible'))

    def test_hidden_file_settings_icon_cannot_keep_a_tooltip(self):
        settings=self.header.findChild(QObject,'openLiveOptions');tooltip=self.attached(settings)
        self.focus(settings);self.assertTrue(tooltip.property('visible'))
        self.header.setProperty('files',True);QTest.qWait(20)
        self.assertFalse(settings.property('visible'));self.assertFalse(tooltip.property('visible'))

    def test_settings_empty_accessible_label_has_no_tooltip(self):
        settings=self.header.findChild(QObject,'openLiveOptions');tooltip=self.attached(settings)
        self.focus(settings);self.assertTrue(tooltip.property('visible'))
        accessible=next(child for child in settings.children() if child.inherits('QQuickAccessibleAttached'))
        accessible.setProperty('name','   ');QTest.qWait(20)
        self.assertFalse(tooltip.property('visible'))
