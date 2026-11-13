import hashlib
import inspect
import multiprocessing as mp
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from screento3d_app import vfg_runtime
from screento3d_app.live_sbs import sbs_worker
from screento3d_app.texture_mailbox import TextureFrame, TexturePool
from screento3d_app.vfg_delivery import TimedMailbox, Timeline


class VfgTests(unittest.TestCase):
    def test_worker_defaults_to_disabled_and_rejects_nonboolean_selection(self):
        self.assertIs(inspect.signature(sbs_worker).parameters['vfg_enabled'].default, False)
        for invalid in (None, 1, 'false'):
            with self.assertRaises(ValueError):
                vfg_runtime.validate_selection(invalid, 'da2-small', 'window', True, True)

    def test_opt_in_requires_supported_capture_renderer_and_model(self):
        for model in vfg_runtime.SUPPORTED_MODELS:
            vfg_runtime.validate_selection(True, model, 'window', True, True)
        for args in (('vda-small', 'window', True, True, 'cuda'),
                     ('da2-small', 'monitor', True, True, 'cuda'),
                     ('da2-base', 'window', False, True, 'cuda'),
                     ('da2-base', 'window', True, False, 'cuda'),
                     ('da2-base', 'window', True, True, 'rowflow-sym')):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    vfg_runtime.validate_selection(True, *args)
                vfg_runtime.validate_selection(False, *args)

    def test_integrity_checks_dependencies_and_bridge_not_only_main_feature(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            names = list(vfg_runtime.PINS)
            pins = {name: hashlib.sha256(name.encode()).hexdigest() for name in names}
            bridge = root / 'bridge.dll'
            bridge.write_bytes(b'bridge')
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
            with patch.object(vfg_runtime, 'PINS', pins), patch.object(
                    vfg_runtime, 'BRIDGE_HASH', hashlib.sha256(b'bridge').hexdigest()):
                vfg_runtime.validate_runtime(root, bridge)
                for name in names:
                    (root / name).write_bytes(b'corrupt')
                    with self.assertRaises(RuntimeError):
                        vfg_runtime.validate_runtime(root, bridge)
                    (root / name).write_bytes(name.encode())
                bridge.unlink()
                with self.assertRaises(RuntimeError):
                    vfg_runtime.validate_runtime(root, bridge)

    def test_timing_lease_is_not_overwritten_and_cut_emits_original_only(self):
        box = TimedMailbox.create(mp.get_context('spawn'))
        box.offer(TexturePool(1, 1, 123, 640, 180, 0, 0, (11, 12)), session=1, owned_pid=123)
        box.install(1, 1)
        timeline = Timeline()
        first = timeline.plan(1_000_000_000, 1_010_000_000, True)
        pair = timeline.plan(1_020_000_000, 1_030_000_000, False)
        self.assertEqual([row[0] for row in first], [0])
        self.assertEqual([row[0] for row in pair], [1, 0])
        for slot, (kind, due, source, oldest) in enumerate(pair):
            frame = TextureFrame(1, 1, slot, slot + 1, source, 1_020_000_000)
            box.publish_timed(frame, due, oldest, kind, 2, 1_030_000_000)
            with self.assertRaises(ValueError):
                box.publish_timed(frame, due, oldest, kind, 2, 1_030_000_000)
            self.assertEqual(box.frame_timing(frame)[4], kind)
            box.release(frame)
        self.assertEqual([r[0] for r in timeline.plan(1_040_000_000, 1_050_000_000, True)], [0])
        with self.assertRaises(RuntimeError):
            Timeline(last_due=2_000_000_000).plan(1_000_000_000, 1_010_000_000, False)
