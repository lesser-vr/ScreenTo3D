import unittest
from review_moge_motion import validate_report


class MogeMotionReviewTests(unittest.TestCase):
    def report(self):
        return dict(status='measured', motion=True, frames_per_source=5,
                    sources={'fixture': 'hash'}, videos=[{}, {}],
                    cases=[dict(source='fixture', model=model, frame=i)
                           for i in range(5) for model in ('da2-trt-fp32', 'moge-fp16-1200')])

    def test_complete_sequence(self):
        validate_report(self.report())

    def test_missing_frame(self):
        report = self.report()
        report['cases'].pop()
        with self.assertRaises(ValueError):
            validate_report(report)

    def test_duplicate_frame(self):
        report = self.report()
        report['cases'][-1]['frame'] = 3
        with self.assertRaises(ValueError):
            validate_report(report)

    def test_incomplete_report(self):
        report = self.report()
        report['status'] = 'incomplete'
        with self.assertRaises(ValueError):
            validate_report(report)
