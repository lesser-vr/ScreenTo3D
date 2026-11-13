"""No OS shutdown is executed: command/process factories and clock are injected."""
import os
from pathlib import Path
import unittest
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication
from screento3d_app.desktop_jobs import ProcessingLease
from screento3d_app.desktop_shutdown import CompletionShutdown,shutdown_command


class CompletionShutdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.now=100.
        self.lease=ProcessingLease()
        self.command=Mock(return_value=('test-only-do-not-execute',['/s','/t','0']))
        self.process=Mock()
        self.power=CompletionShutdown(self.lease,clock=lambda:self.now,command=self.command,
                                      process_factory=Mock(return_value=self.process))
        self.addCleanup(self.power.timer.stop)
        self.addCleanup(self.power.deleteLater)

    def test_default_off_never_requests_shutdown(self):
        self.power.begin();self.now+=100;self.power._tick()
        self.assertFalse(self.power.selected);self.assertFalse(self.power.pending)
        self.command.assert_not_called();self.assertIsNone(self.lease.owner)

    def test_explicit_countdown_waits_full_time_and_owns_lease(self):
        self.power.setSelected(True);self.power.begin()
        self.assertTrue(self.power.pending);self.assertEqual(self.lease.owner,'shutdown')
        self.now+=29.1;self.power._tick()
        self.assertEqual(self.power.seconds,1);self.command.assert_not_called()
        self.now+=.9;self.power._tick()
        self.command.assert_called_once();self.process.start.assert_called_once()
        self.process.setProgram.assert_called_once_with('test-only-do-not-execute')
        self.power._finish(True)
        self.assertIsNone(self.lease.owner);self.assertFalse(self.power.selected)

    def test_cancel_clears_timer_and_late_ticks_cannot_shutdown(self):
        self.power.setSelected(True);self.power.begin();self.power.cancel()
        self.now+=100;self.power._tick()
        self.command.assert_not_called();self.assertIsNone(self.lease.owner)
        self.assertFalse(self.power.timer.isActive());self.assertFalse(self.power.selected)

    def test_cannot_arm_during_processing(self):
        self.lease.acquire('file');self.power.setSelected(True)
        self.assertFalse(self.power.selected)

    def test_failed_os_request_releases_lease_and_reports_stable_id(self):
        failures=[];self.power.errorOccurred.connect(failures.append)
        self.power.setSelected(True);self.power.begin();self.now+=30;self.power._tick()
        self.power._finish(False)
        self.assertEqual(failures[0].error_id,'E_SHUTDOWN_FAILED')
        self.assertIsNone(self.lease.owner);self.assertFalse(self.power.selected)

    @unittest.skipUnless(os.name=='nt','Windows command path only')
    def test_os_command_uses_trusted_absolute_path_and_no_force_or_os_delay(self):
        # Resolves a path only, never starts the returned command.
        program,args=shutdown_command()
        self.assertTrue(Path(program).is_absolute());self.assertEqual(Path(program).name,'shutdown.exe')
        self.assertNotIn('/f',args);self.assertEqual(args[args.index('/t')+1],'0')
