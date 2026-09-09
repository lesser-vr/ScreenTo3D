"""Diagnostic-only source-region tracing; never imported by the application.

Exclusive host wall intervals include native work/waits within a region. Optional
CUDA events enclose TRT submission, not CPU preprocessing or an end-to-end frame.
The source anchors fail closed if the measured implementation changes.
"""

from collections import defaultdict
import inspect
import sys
import time


def region_plan(function, anchors):
    lines, first = inspect.getsourcelines(function)
    result = {}
    for prefix, label in anchors:
        matches = [first + i for i, line in enumerate(lines)
                   if line.strip().startswith(prefix)]
        if len(matches) != 1:
            raise ValueError(f"Expected one source anchor in {function.__qualname__}: {prefix}")
        if matches[0] in result:
            raise ValueError("Duplicate region boundary")
        result[matches[0]] = label
    return function.__code__, result


class SourceRegions:
    """Trace only registered frames, charging each wall interval once."""

    def __init__(self, plans, transition=None, clock=time.perf_counter_ns):
        self.plans = dict(plans)
        self.transition = transition
        self.clock = clock
        self.elapsed = defaultdict(int)
        self.stack = []
        self.current = "probe_overhead"
        self.last = None
        self.previous_trace = None

    def _change(self, label):
        now = self.clock()
        self.elapsed[self.current] += now - self.last
        old = self.current
        self.current = label
        self.last = now
        if old != label and self.transition is not None:
            self.transition(old, label)

    def _trace(self, frame, event, arg):
        plan = self.plans.get(frame.f_code)
        if plan is None:
            return None
        if event == "call":
            self.stack.append((frame, self.current))
            self._change("probe_overhead")
        elif event == "line":
            label = plan.get(frame.f_lineno)
            if label is not None:
                self._change(label)
        elif event == "return":
            if not self.stack or self.stack[-1][0] is not frame:
                raise RuntimeError("Diagnostic trace stack mismatch")
            _, previous = self.stack.pop()
            self._change(previous)
        return self._trace

    def __enter__(self):
        self.previous_trace = sys.gettrace()
        if self.previous_trace is not None:
            raise RuntimeError("Refusing to replace an existing debugger/profiler")
        self.last = self.clock()
        sys.settrace(self._trace)
        return self

    def __exit__(self, kind, value, traceback):
        sys.settrace(self.previous_trace)
        self._change("probe_overhead")
        self.stack.clear()
        return False


def model_plans(model, engine):
    complete = region_plan(type(engine).complete_device, [
        ("token.validate()", "token_validation"),
        ("self.stream.synchronize()", "completion_wait"),
        ("self.pending_device = None", "completion_bookkeeping"),
    ])
    if model == "vda":
        from depthsbs_app.vda_preprocess import preprocess

        return [complete, region_plan(type(engine).infer_device, [
            ("self._check()", "input_checks"),
            ("started = time.perf_counter()", "preprocessing"),
            ("if self.shape is not None", "input_upload"),
            ("resized = torch.nn.functional.interpolate(", "upscale"),
            ("if not bool(torch.isfinite(resized).all())", "resized_validation"),
            ("self.calls += 1", "token_bookkeeping"),
        ]), region_plan(engine._execute, [
            ("warmup = not self.history", "cache_prepare_bind"),
            ("if not context.execute_async_v3(", "trt_enqueue"),
            ("self.stream.synchronize()", "trt_wait"),
            ("if not all(torch.isfinite", "output_validation"),
            ("cache = tuple(outputs", "cache_update"),
        ]), region_plan(preprocess, [
            ("if not isinstance(frame", "preprocess_checks"),
            ("image = cv2.resize(", "preprocess_float_resize"),
            ("normalized =", "preprocess_normalize_layout"),
        ])]
    if model == "ovda":
        return [complete, region_plan(type(engine).infer_device, [
            ("self.check()", "input_checks"),
            ("self.pre.preprocess(frame.copy())", "input_copy_upload"),
            ("if not self.cache:", "cache_prepare_bind"),
            ("if not self.context.execute_async_v3(", "trt_enqueue"),
            ("self.stream.synchronize()", "trt_wait"),
            ("if not all(", "output_validation"),
            ("if self.used == 15:", "cache_update"),
            ("result = torch.nn.functional.interpolate(", "upscale"),
            ("self.calls += 1", "token_bookkeeping"),
        ]), region_plan(engine.pre.preprocess, [
            ("if not isinstance(frame", "preprocess_checks"),
            ("x=torch.from_numpy", "preprocess_float"),
            ("if x.max()", "preprocess_scale"),
            ("h,w=frame.shape", "preprocess_shape"),
            ("if (h,w)!=(nh,nw):", "preprocess_resize"),
            ("return (x-self.mean)/self.std", "preprocess_normalize_layout"),
        ])]
    raise ValueError("Unsupported diagnostic model")
