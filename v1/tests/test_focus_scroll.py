"""Pointer and keyboard interaction with the production scroll view."""
from pathlib import Path
import unittest

from PySide6.QtCore import QObject, QPoint, QUrl, Qt
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import shiboken6


class FocusScrollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        QQuickStyle.setStyle('Basic')

    def setUp(self):
        qml = Path(__file__).resolve().parents[1] / 'screento3d_app' / 'qml'
        source = '''
import QtQuick
import QtQuick.Controls.Basic
import "APP_QML" as UI
ApplicationWindow {
    width: 260; height: 150; visible: true
    UI.FocusScrollView {
        objectName: "scroll"
        anchors.fill: parent
        Item {
            implicitWidth: 240; implicitHeight: 430
            UI.ActionButton {
                objectName: "first"; x: 20; y: 28; width: 120
                text: "First action"
            }
            UI.ActionButton {
                objectName: "last"; x: 20; y: 340; width: 120
                text: "Last action"
            }
        }
    }
}'''.replace('APP_QML', qml.as_uri())
        self.engine = QQmlApplicationEngine()
        self.addCleanup(shiboken6.delete, self.engine)
        self.engine.loadData(source.encode(), QUrl.fromLocalFile(str(qml.parent / 'focus-fixture.qml')))
        self.assertTrue(self.engine.rootObjects())
        self.window = self.engine.rootObjects()[0]
        self.addCleanup(self.window.close)
        self.window.requestActivate()
        self.flick = self.window.findChild(QObject, 'scroll').property('contentItem')
        self.first = self.window.findChild(QObject, 'first')
        self.last = self.window.findChild(QObject, 'last')
        QTest.qWait(80)

    def test_click_near_scroll_edge_keeps_button_in_place(self):
        # The button is fully visible, starting 2 px below the top of the view.
        self.assertTrue(self.flick.setProperty('contentY', 26.0))
        clicked = []
        self.first.clicked.connect(lambda: clicked.append(True))
        QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, QPoint(70, 4))
        try:
            QTest.qWait(45)
            self.assertTrue(self.first.property('pressed'))
            offset = self.flick.property('contentY')
            QTest.mouseMove(self.window, QPoint(70, 5))
            QTest.qWait(20)
        finally:
            QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, QPoint(70, 5))
        self.assertAlmostEqual(offset, 26.0)
        self.assertEqual(clicked, [True])

    def test_tab_and_shift_tab_reveal_controls_in_both_directions(self):
        self.first.forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(25)
        self.assertIs(self.window.activeFocusItem(), self.first)
        QTest.keyClick(self.window, Qt.Key_Tab)
        QTest.qWait(35)
        self.assertIs(self.window.activeFocusItem(), self.last)
        self.assertGreaterEqual(self.flick.property('contentY') + 150, 380)
        QTest.keyClick(self.window, Qt.Key_Tab, Qt.ShiftModifier)
        QTest.qWait(35)
        self.assertIs(self.window.activeFocusItem(), self.first)
        self.assertLessEqual(self.flick.property('contentY'), 28)


if __name__ == '__main__':
    unittest.main()
