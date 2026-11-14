import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from screento3d_app.shortcut_help import ShortcutHelp
from screento3d_app.shortcut_keys import FULLSCREEN,VFG


class Live(QObject):
    changed=Signal()
    def __init__(self):
        super().__init__()
        self.active=self.stoppingNow=self.vfgSwitching=False
        self.hasFrame=True; self.vfgConfigurable=True; self.vfgEnabled=False
        self.vfgUnavailableReason=''
        self.output_policy=SimpleNamespace(state=False,registered=False)
        self.toggleOutputFullscreen=Mock(); self.toggleVfg=Mock()


class ShortcutHelpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.live=Live(); self.vfg=SimpleNamespace(registered=True)
        self.help=ShortcutHelp(self.live,self.vfg)
    def start(self):
        self.live.active=True; self.live.output_policy.state=True
        self.live.output_policy.registered=True; self.live.changed.emit()
    def test_idle_fullscreen_is_not_reported_as_conflicting(self):
        self.assertFalse(self.help.groups[0]['rows'][0]['conflict'])
        self.assertEqual(self.help.notice,'')
        self.assertEqual(len(self.help.groups[1]['rows']),2)
    def test_guide_keys_and_actual_win32_registration_share_definitions(self):
        from screento3d_app.output_window import OutputWindowPolicy
        from screento3d_app.vfg_hotkey import VfgHotkey
        self.assertEqual((FULLSCREEN.keys,FULLSCREEN.identifier),(OutputWindowPolicy.shortcut,OutputWindowPolicy.identifier))
        self.assertEqual((VFG.keys,VFG.identifier,VFG.key,VFG.modifiers),(VfgHotkey.shortcut,VfgHotkey.identifier,VfgHotkey.key,VfgHotkey.modifiers))
    def test_conflict_shows_fallback_and_one_nonblocking_notice_per_session(self):
        self.start(); self.live.output_policy.registered=False; self.live.changed.emit()
        self.assertIn(FULLSCREEN.keys,self.help.notice)
        row=self.help.groups[0]['rows'][0]
        self.assertTrue(row['conflict']); self.assertTrue(row['enabled'])
        self.help.activate(row['action']);self.live.toggleOutputFullscreen.assert_called_once()
        self.help.clear_notice();self.live.changed.emit();self.assertEqual(self.help.notice,'')
        self.live.active=False;self.live.changed.emit();self.start()
        self.live.output_policy.registered=False;self.live.changed.emit()
        self.assertIn(FULLSCREEN.keys,self.help.notice)
    def test_vfg_conflict_preserves_button_with_compatibility_reason(self):
        self.vfg.registered=False;self.live.vfgUnavailableReason='Unsupported source'
        self.start();row=self.help.groups[0]['rows'][1]
        self.assertTrue(row['conflict']);self.assertFalse(row['enabled'])
        self.assertEqual(row['detail'],'Unsupported source')
    def test_repeated_runtime_stats_do_not_rebuild_the_guide(self):
        self.start();changed=Mock();self.help.changed.connect(changed)
        for _ in range(120):self.live.changed.emit()
        changed.assert_not_called()
    def test_comparison_modes_hide_vfg_shortcut(self):
        self.live.vfgConfigurable=False;self.live.changed.emit()
        self.assertEqual(len(self.help.groups[0]['rows']),1)
    def test_stopped_or_switching_sessions_cannot_trigger_duplicate_vfg(self):
        self.help.activate('vfg');self.live.toggleVfg.assert_not_called()
        self.start();self.live.vfgSwitching=True
        self.help.activate('vfg');self.live.toggleVfg.assert_not_called()
        self.live.vfgSwitching=False;self.help.activate('vfg');self.live.toggleVfg.assert_called_once()
