import hashlib
from pathlib import Path
import tempfile
import unittest
import numpy as np
from screento3d_app.stereo import refine_flat_background
from uniform_background_tc import load_case,verify_asset,fixture_path,generated_frames,observe_pattern,assess_performance


class UniformBackgroundTcTests(unittest.TestCase):
    def test_fixture_is_a_small_independent_excerpt(self):
        case=load_case()
        self.assertEqual(case['frames']/case['fps'],case['duration_seconds'])
        self.assertLessEqual(case['duration_seconds'],2)
        self.assertLess(case['bytes'],10*1024**2)
        self.assertFalse(Path(case['path']).is_absolute())
        self.assertEqual(len(case['sha256']),64)

    def test_missing_corrupt_and_escaping_assets_fail_explicitly(self):
        case=load_case()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with self.assertRaises(FileNotFoundError):verify_asset(case,root)
            path=fixture_path(case,root);path.parent.mkdir(parents=True);path.write_bytes(b'bad clip')
            with self.assertRaises(ValueError):verify_asset(case,root)
            fixture=dict(case,bytes=8,sha256=hashlib.sha256(b'bad clip').hexdigest())
            self.assertEqual(verify_asset(fixture,root),path)
            with self.assertRaises(ValueError):fixture_path(dict(case,path='../private.mp4'),root)

    def test_moving_fixture_exercises_background_correction(self):
        case=load_case();frames=list(generated_frames(frames=4))
        self.assertFalse(np.array_equal(frames[0],frames[-1]))
        for rgb in frames:
            observation=observe_pattern(rgb,case)
            self.assertTrue(observation['qualifies'])
            raw=np.tile(np.linspace(.1,.9,rgb.shape[1],dtype=np.float32),(rgb.shape[0],1))
            corrected=refine_flat_background(rgb,raw)
            self.assertIsNot(corrected,raw)
            background=np.max(rgb,axis=2)==0
            values=corrected[background]
            np.testing.assert_array_equal(values,np.full_like(values,values[0]))
        plain=np.zeros_like(frames[0]);self.assertFalse(observe_pattern(plain,case)['qualifies'])
        noisy=frames[0].copy();noisy[0,::2]=255
        self.assertFalse(observe_pattern(noisy,case)['qualifies'])

    def report(self,normal=60,control=62,background=1):
        rows=[]
        for size in load_case()['performance']['sizes']:
            for mode,fps in ((None,normal),(False,control)):
                rows.append(dict(clip='flower',size=size,background=mode,
                                 windows=[dict(fps=fps,cpu_background_ms=dict(median=background if mode is None else 0)) for _ in range(4)]))
        return dict(rows=rows)

    def test_performance_case_rejects_the_observed_collapse(self):
        result=assess_performance(self.report(13.5,39.2,59),load_case())
        self.assertEqual(result['status'],'failed')
        self.assertTrue(all(len(r['reasons'])==2 for r in result['results']))
        self.assertEqual(assess_performance(self.report(),load_case())['status'],'passed')
        current=self.report()
        for row in current['rows']:
            for window in row['windows']:window['background_ms']=window.pop('cpu_background_ms')
        self.assertEqual(assess_performance(current,load_case())['status'],'passed')

    def test_slow_source_or_missing_baseline_cannot_count_as_pass(self):
        self.assertEqual(assess_performance(self.report(10,10,0),load_case())['status'],'inconclusive')
        report=self.report();report['rows'].pop()
        self.assertEqual(assess_performance(report,load_case())['status'],'inconclusive')

    def test_source_ceiling_cannot_hide_expensive_background_work(self):
        self.assertEqual(assess_performance(self.report(10,10,59),load_case())['status'],'failed')

    def test_nonfinite_or_invalid_timing_cannot_pass(self):
        for value in (float('nan'),float('inf'),-1,True):
            self.assertNotEqual(assess_performance(self.report(background=value),load_case())['status'],'passed')


if __name__=='__main__':unittest.main()
