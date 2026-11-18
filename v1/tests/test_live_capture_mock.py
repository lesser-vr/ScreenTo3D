"""Deterministic capture substitutions exercised through the real SBS worker."""
from contextlib import ExitStack, contextmanager, nullcontext
from dataclasses import replace
import multiprocessing as mp
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from screento3d_app import capture_sources
from screento3d_app.capture_mailbox import FAILED, STATE, STOPPED, Mailbox
from screento3d_app.live_diagnostics import WorkerDiagnostics
from screento3d_app.live_model import model_adapter
from screento3d_app.live_sbs import (
    PROCESSED, RESET_GAP, RESET_RESIZE, RESET_START, STAT_COUNT,
    reset_reason, resolve_history_policy, sbs_worker,
)
from screento3d_app.messages import decode_message


@contextmanager
def fake_trt_import():
    name = 'screento3d_app.trt_backend'
    original = sys.modules.get(name)
    sys.modules[name] = SimpleNamespace(DepthEngine=object)
    try:
        yield
    finally:
        if original is None:
            del sys.modules[name]
        else:
            sys.modules[name] = original


class FakeFrame:
    def __new__(cls, pixels, engine):
        return pixels


class Projection:
    h2d = d2h = syncs = 0
    gpu_ms = np.zeros(8)
    projection_ms = np.zeros(6)
    last = {'background_ms': 0}

    def reset(self):
        pass

    def configure_live_quality(self, quality):
        pass

    def inspect_scene(self, frame):
        return SimpleNamespace(cut=False)

    def infer(self, frame):
        return None

    def render(self, frame, depth, *, scene):
        return np.concatenate((frame, frame), axis=1)


class WorkerMockTests(unittest.TestCase):
    def run_worker(self, steps):
        context = mp.get_context('spawn')
        output = Mailbox.create(context, metadata_only=True)
        output.pixels = bytearray(128*72*8)
        diagnostics = WorkerDiagnostics.create(context)
        stats = [0]*STAT_COUNT
        iterator = iter(steps)
        idle = []
        resets = Mock()
        engine = SimpleNamespace(device=0, gpu_input=SimpleNamespace(execution=SimpleNamespace(stream=None)))
        adapter = replace(model_adapter('da2-small'), gpu_capture_engine=lambda _: nullcontext(engine),
                          renderer=lambda native, gpu_capture: lambda *args: nullcontext(Projection()))

        def read(stream):
            step = next(iterator, 'stop')
            if step == 'stop':
                output.stop.set()
                return None
            if isinstance(step, Exception):
                raise step
            if step is None:
                idle.append((stats[PROCESSED], diagnostics.snapshot()['accepted_frames']))
                return None
            seq, stamp_ms, width, height, resizes = step
            timestamp = stamp_ms*1_000_000
            pixels = np.full((height,width,3), seq, np.uint8)
            return pixels, dict(width=width, height=height, sequence=seq,
                                source_ns=timestamp, callback_ns=timestamp+1, replaced=0, resizes=resizes)

        with ExitStack() as stack:
            stack.enter_context(fake_trt_import())
            stack.enter_context(patch('screento3d_app.resources.configure_resource_root'))
            stack.enter_context(patch('screento3d_app.live_sbs.model_adapter', return_value=adapter))
            stack.enter_context(patch('screento3d_app.depth_backend.BackendBinding.reset', resets))
            stack.enter_context(patch('screento3d_app.gpu_usage.UsageSampler.current_cuda',
                                      return_value=SimpleNamespace(poll=lambda now:None, close=lambda:None)))
            stack.enter_context(patch('screento3d_app.gpu_capture.GpuCapture',
                                      return_value=nullcontext(SimpleNamespace(read=read))))
            stack.enter_context(patch('screento3d_app.gpu_frame.GpuFrame', FakeFrame))
            sbs_worker(dict(kind='window',width=64,height=36), False, output, stats, .5,
                       mode='performance', gpu_candidate=True, gpu_capture_snapshot=True,
                       renderer_snapshot='cuda', stereo_layout='half-tb', worker_diagnostics=diagnostics)
        return output, stats, diagnostics.snapshot(), idle, [call.args[1] for call in resets.call_args_list]

    def test_no_frame_gaps_and_timestamp_reversal_resume_processing(self):
        steps = [(1,1000,64,36,0)]
        for gap in (100,250,500):
            seq, stamp, width, height, count = steps[-1]
            steps += [None, None, (seq+1,stamp+gap,width,height,count)]
        steps += [(5,1100,64,36,0), (7,1116,64,36,0), (8,1132,128,72,1)]
        output, stats, diagnostics, idle, reasons = self.run_worker(steps)
        self.assertEqual(output.meta[STATE], STOPPED, bytes(output.error.value))
        self.assertEqual(stats[PROCESSED], 7)
        self.assertEqual(idle, [(1,1),(1,1),(2,2),(2,2),(3,3),(3,3)])
        self.assertEqual([stats[i] for i in (RESET_START,RESET_GAP,RESET_RESIZE)], [1,3,1])
        self.assertEqual(reasons, ['start','discontinuity','discontinuity','discontinuity','source_change'])
        self.assertEqual(diagnostics['source_clock_regressions'], 1)
        self.assertEqual(diagnostics['max_source_gap_ns'], 500_000_000)
        self.assertEqual(diagnostics['resizes'], 1)

    def test_capture_exception_reaches_mailbox_and_worker_diagnostics(self):
        output, stats, diagnostics, _, _ = self.run_worker(
            [(1,1000,64,36,0), None, RuntimeError('mock capture HRESULT 0x887A0005')])
        self.assertEqual(output.meta[STATE], FAILED)
        self.assertEqual(stats[PROCESSED], 1)
        self.assertIn('0x887A0005', decode_message(bytes(output.error.value)).details)
        self.assertIn('0x887A0005', diagnostics['failure']['traceback'])
        self.assertTrue(output.stop.is_set())

    def test_reused_or_hidden_source_is_rejected(self):
        source = dict(kind='window', id=123, pid=42)
        for pid, minimized, expected in (
            (99, False, 'E_CAPTURE_SOURCE_CLOSED'),
            (42, True, 'E_CAPTURE_SOURCE_HIDDEN'),
        ):
            api = Mock()
            api.IsWindow.return_value = True
            api.IsIconic.return_value = minimized
            api.IsWindowVisible.return_value = True
            api.GetWindowThreadProcessId.side_effect = lambda _, out: setattr(out._obj, 'value', pid)
            with self.subTest(pid=pid, minimized=minimized), \
                    patch.object(capture_sources, 'user32', api), \
                    patch.object(capture_sources, 'require_input_desktop'), \
                    patch.object(capture_sources, 'is_sbs_output', return_value=False):
                with self.assertRaises(ValueError) as raised:
                    capture_sources.validate_source(source)
                self.assertEqual(raised.exception.args[0].error_id, expected)

    def test_model_specific_policy_for_increasing_sequence_and_clock(self):
        size = (1920,1080)
        for model, skip_two in (('da2-small', None), ('da2-base', None), ('vda-small', 'gap')):
            policy = resolve_history_policy(model, 'continuous')
            def reason(sequence, offset_ms, shape=size):
                return reset_reason(10,sequence,size,shape,False,previous_source_ns=1_000_000_000,
                                    source_ns=1_000_000_000+offset_ms*1_000_000,**policy)

            with self.subTest(model=model):
                self.assertIsNone(reason(12,33))
                self.assertEqual(reason(13,49), skip_two)
                self.assertEqual(reason(11,101), 'gap')
                self.assertEqual(reason(11,-1), 'gap')
                self.assertEqual(reason(11,16,(1280,720)), 'resize')


if __name__ == '__main__':
    unittest.main()
