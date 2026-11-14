"""Focus restoration never overrides a user's later choice of another app."""
import unittest
import os
from screento3d_app.output_focus import FocusSession


class FakeWindows:
    def __init__(self):
        self.current = 10
        self.windows = {10: 1, 11: 1, 12: 1, 20: 2, 30: 3}
        self.invalid = set()
        self.activated = []

    def identity(self, hwnd):
        return (hwnd, self.windows[hwnd]) if hwnd in self.windows else None

    def usable(self, target):
        return bool(target and self.identity(target[0]) == target and target[0] not in self.invalid)

    def is_renderer(self, hwnd):
        return False

    def foreground(self):
        return self.current

    def belongs(self, hwnd, owner):
        return hwnd in (owner, 12)  # Output plus its owned menu.

    def activate(self, target):
        self.activated.append(target)
        self.current = target[0]
        return True


class OutputFocusTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeWindows()
        self.focus = FocusSession(self.api, main=10, output=11)
        self.source = dict(kind='window', id=20, pid=2)

    def test_first_frame_returns_to_validated_source_once(self):
        self.focus.arm(self.source)
        self.focus.ready(); self.focus.ready()
        self.assertEqual(self.api.activated, [(20, 2)])

    def test_late_ready_does_not_steal_from_other_app_or_error_dialog(self):
        for foreground in (30, 12):
            self.api.current = 10; self.focus.arm(self.source)
            self.api.current = foreground; self.focus.ready()
            self.assertEqual(self.api.activated, [])

    def test_monitor_capture_does_not_choose_a_window(self):
        self.focus.arm(dict(kind='monitor', id=1, pid=0)); self.focus.ready()
        self.assertEqual(self.api.activated, [])

    def test_recycled_hidden_or_minimized_source_is_never_activated(self):
        self.focus.arm(self.source); self.api.windows[20] = 9; self.focus.ready()
        self.assertEqual(self.api.activated, [])
        self.api.windows[20] = 2; self.api.invalid.add(20)
        self.focus.arm(self.source); self.focus.ready()
        self.assertEqual(self.api.activated, [])

    def test_management_returns_to_previous_external_input_target(self):
        self.focus.arm(self.source); self.focus.pending = False
        self.api.current = 30; self.focus.begin()
        self.api.current = 12; self.focus.finish()
        self.assertEqual(self.api.activated, [(30, 3)])

    def test_source_fallback_when_management_starts_from_output(self):
        self.focus.arm(self.source); self.focus.pending = False
        self.api.current = 11; self.focus.begin(); self.focus.finish()
        self.assertEqual(self.api.activated, [(20, 2)])

    def test_management_never_pulls_focus_back_from_user_selected_app(self):
        self.focus.arm(self.source); self.api.current = 20; self.focus.begin()
        self.api.current = 30; self.focus.finish()
        self.assertEqual(self.api.activated, [])

    def test_cancel_clears_deferred_start_and_management(self):
        self.focus.arm(self.source); self.focus.begin(); self.focus.cancel()
        self.api.current = 11; self.focus.ready(); self.focus.finish()
        self.assertEqual(self.api.activated, [])
        self.assertFalse(self.focus.managing)

    def test_inaccessible_foreground_does_not_restore_an_unverified_window(self):
        self.focus.arm(self.source); self.api.current = 99; self.focus.begin()
        self.api.current = 11; self.focus.finish()
        self.assertEqual(self.api.activated, [(20, 2)])
    def test_preparing_frame_does_not_interrupt_an_open_output_menu(self):
        self.focus.arm(self.source); self.focus.begin(); self.api.current=11
        self.focus.ready()
        self.assertEqual(self.api.activated, [])
        self.focus.finish()
        self.assertEqual(self.api.activated, [(20,2)])

    def test_owl_renderer_is_not_mistaken_for_the_original_input_window(self):
        self.focus.arm(self.source); self.api.current=30
        self.api.is_renderer=lambda hwnd: hwnd==30
        self.focus.begin(); self.api.current=11; self.focus.finish()
        self.assertEqual(self.api.activated, [(20,2)])


class OutputWindowBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QObject, Signal, QRect
        from unittest.mock import Mock
        from screento3d_app.output_window import OutputWindowPolicy
        from PySide6.QtGui import QWindow
        class Window(QObject):
            visibleChanged = Signal(bool)
            def __init__(self, hwnd):
                super().__init__(); self.hwnd = hwnd; self.shown = True; self.fullscreen = False; self.rect = QRect(0,0,400,200)
            def winId(self): return self.hwnd
            def geometry(self): return self.rect
            def isVisible(self): return self.shown
            def visibility(self): return QWindow.FullScreen if self.fullscreen else QWindow.Windowed
            def showNormal(self): self.fullscreen = False
            def showFullScreen(self): self.fullscreen = True
        class Live(QObject):
            changed = Signal()
            frameChanged = Signal()
            def __init__(self):
                super().__init__(); self.active = True; self.stoppingNow = False
                self.vfgSwitching = False; self.hasFrame = True
                self.output_window = Window(11); self.rememberOutput = Mock()
        self.api = FakeWindows(); self.api.user = Mock()
        self.api.watch_windows = Mock(return_value=([], None))
        self.api.unwatch_windows = Mock()
        self.api.noactivate = Mock(); self.api.order = Mock(); self.api.place = Mock()
        self.live = Live(); self.main = Window(10)
        self.policy = OutputWindowPolicy(self.app, self.live, self.main, api=self.api)
        self.addCleanup(self.policy.close)
        self.policy.arm(dict(kind='window', id=20, pid=2))
        self.policy.sync()

    def message(self, code, lparam=0, wparam=0, hwnd=11):
        import ctypes as C
        from ctypes import wintypes as W
        msg = W.MSG(); msg.hWnd = hwnd; msg.message = code
        msg.wParam = wparam; msg.lParam = lparam
        return self.policy.nativeEventFilter(b'windows_generic_MSG', C.addressof(msg))

    def test_title_bar_selection_waits_for_f11_then_returns_to_original(self):
        self.api.current=20
        self.message(0x21,(0x201<<16)|2)
        self.api.current=11
        self.message(0x231); self.message(0x232); self.message(0xA2)
        self.app.processEvents()
        self.assertTrue(self.policy.focus.managing)
        self.assertEqual(self.api.activated,[])
        self.policy.toggle_fullscreen()  # The F11 QML slot.
        self.app.processEvents()
        self.assertTrue(self.live.output_window.fullscreen)
        self.assertFalse(self.policy.focus.managing)
        self.assertEqual(self.api.activated,[(20,2)])
        self.api.noactivate.assert_called_with(11,True)

    def test_fullscreen_completion_does_not_override_a_new_foreground_app(self):
        self.api.current=20; self.policy.begin('caption'); self.api.current=11
        self.policy.toggle_fullscreen()
        self.api.current=30; self.app.processEvents()
        self.assertEqual(self.api.activated,[])
        self.assertFalse(self.policy.focus.managing)

    def test_background_activation_message_does_not_unlock_playback_focus(self):
        self.api.current=30
        self.message(0x6,wparam=1)
        self.assertFalse(self.policy.focus.managing)
        self.api.noactivate.assert_called_with(11,True)

    def test_client_click_is_delivered_without_activation_and_right_click_can_manage(self):
        self.assertEqual(self.message(0x21, (0x201 << 16) | 1), (True, 3))
        self.assertFalse(self.policy.focus.managing)
        self.assertEqual(self.message(0x21, (0x204 << 16) | 1), (True, 1))
        self.assertTrue(self.policy.focus.managing)
        self.policy.begin('menu'); self.api.current = 11
        self.policy.end('menu')
        self.assertEqual(self.api.activated, [(20, 2)])
        self.api.noactivate.assert_called_with(11, True)

    def test_move_and_resize_restores_after_modal_loop(self):
        self.api.current = 20
        self.message(0x21, (0x201 << 16) | 2)
        self.message(0x231); self.api.current = 11
        self.live.output_window.rect=self.live.output_window.rect.adjusted(0,0,5,5)
        self.message(0x232); self.app.processEvents()
        self.assertFalse(self.policy.focus.managing)
        self.assertEqual(self.api.activated, [(20, 2)])

    def test_style_rewrite_preserves_noactivate_in_fullscreen(self):
        import ctypes as C
        from screento3d_app.output_window import StyleChange
        from screento3d_app.output_focus import NOACTIVATE
        style = StyleChange(0, 0)
        self.message(0x7c, C.addressof(style), -20)
        self.assertTrue(style.new & NOACTIVATE)
        self.policy.begin('menu'); self.message(0x7c, C.addressof(style), -20)
        self.assertFalse(style.new & NOACTIVATE)

    def test_fullscreen_hotkey_and_settings_fallback_do_not_change_foreground(self):
        self.api.current = 20
        self.policy.toggle_fullscreen()
        self.assertTrue(self.live.output_window.fullscreen)
        self.message(0x312, wparam=self.policy.identifier); self.app.processEvents()
        self.assertFalse(self.live.output_window.fullscreen)
        self.assertEqual(self.api.activated, [])
        self.assertEqual(self.api.current, 20)

    def test_vfg_restart_does_not_clear_original_input_target_or_hotkey(self):
        self.live.vfgSwitching = True; self.live.stoppingNow = True
        self.policy.sync(); self.live.active = False; self.policy.sync()
        self.assertEqual(self.policy.focus.source, (20, 2))
        self.assertTrue(self.policy.registered)
        self.api.user.UnregisterHotKey.assert_not_called()

    def test_stop_cancels_pending_restore_and_releases_global_hotkey(self):
        self.live.active = False; self.live.output_window.shown = False
        self.policy.sync(); self.policy.first_frame()
        self.assertEqual(self.api.activated, [])
        self.assertFalse(self.policy.registered)
        self.api.user.UnregisterHotKey.assert_called_once_with(None, self.policy.identifier)

    def test_hotkey_conflict_leaves_settings_fullscreen_available(self):
        self.live.active = False; self.policy.sync()
        self.api.user.RegisterHotKey.return_value = False
        self.live.active = True; self.policy.sync()
        self.assertFalse(self.policy.registered)
        self.assertIn('Cannot register', str(self.live.output_shortcut))
        self.policy.toggle_fullscreen()
        self.assertTrue(self.live.output_window.fullscreen)

    def test_client_frame_notifications_do_not_poll_or_reorder_windows(self):
        self.policy.first_frame(); self.app.processEvents()
        self.api.order.reset_mock()
        for _ in range(120):
            self.live.frameChanged.emit(); self.live.changed.emit()
        self.app.processEvents()
        self.api.order.assert_not_called()


class OutputOrderingTests(unittest.TestCase):
    def test_native_ordering_stays_behind_owl_renderer_and_keeps_controls_accessible(self):
        from unittest.mock import Mock, call
        from screento3d_app.output_focus import Win32Windows, TOPMOST
        api = object.__new__(Win32Windows)
        api.foreground = Mock(return_value=20)
        api.identity = Mock(return_value=(20, os.getpid()+1))
        api.belongs = Mock(return_value=False)
        api.renderer_above = Mock(return_value=None)
        api.place = Mock(); api.user = Mock(); api.user.GetWindow.return_value=0
        api.order(11)
        api.place.assert_called_once_with(11, -1)
        api.place.reset_mock(); api.renderer_above.return_value=88
        api.user.GetWindowLongPtrW.return_value=TOPMOST
        api.order(11); api.place.assert_called_once_with(11, 88)
        api.place.reset_mock(); api.user.GetWindowLongPtrW.return_value=0
        api.order(11)
        self.assertEqual(api.place.call_args_list,[call(11,-2),call(11,88)])
        api.place.reset_mock(); api.identity.return_value=(10,os.getpid())
        api.renderer_above.return_value=None
        api.order(11)
        self.assertEqual(api.place.call_args_list,[call(11,-2),call(11,20)])
