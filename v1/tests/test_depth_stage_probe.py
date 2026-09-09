import sys
import unittest

from depth_stage_probe import SourceRegions, region_plan


def inner():
    value = sum(range(10))
    return value


def outer():
    before = 1
    result = inner()
    after = result + before
    return after


def failing():
    raise ValueError("fixture")


class StageProbeTests(unittest.TestCase):
    def test_trace_preserves_result_and_exclusive_accounting(self):
        ticks = iter(range(0, 10000, 10))
        plans = [region_plan(outer, [("before =", "before"), ("after =", "after")]),
                 region_plan(inner, [("value =", "inner")])]
        trace = SourceRegions(plans, clock=lambda: next(ticks))
        with trace:
            self.assertEqual(outer(), 46)
        self.assertIsNone(sys.gettrace())
        self.assertEqual(sum(trace.elapsed.values()), trace.last)
        self.assertGreater(trace.elapsed["inner"], 0)
        self.assertGreater(trace.elapsed["before"], 0)
        self.assertGreater(trace.elapsed["after"], 0)

    def test_missing_and_duplicate_anchor_rejected(self):
        with self.assertRaises(ValueError):
            region_plan(outer, [("not_a_line", "bad")])
        with self.assertRaises(ValueError):
            region_plan(outer, [("before", "one"), ("before", "two")])

    def test_exception_restores_trace(self):
        with self.assertRaisesRegex(ValueError, "fixture"):
            with SourceRegions([region_plan(failing, [("raise", "failure")])]):
                failing()
        self.assertIsNone(sys.gettrace())

    def test_existing_trace_is_not_replaced(self):
        def existing(frame, event, arg):
            return None
        sys.settrace(existing)
        try:
            with self.assertRaises(RuntimeError):
                with SourceRegions([]):
                    pass
            self.assertIs(sys.gettrace(), existing)
        finally:
            sys.settrace(None)


if __name__ == "__main__":
    unittest.main()
