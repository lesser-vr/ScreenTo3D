import unittest
from unittest.mock import Mock
from pathlib import Path
import numpy as np
from depthsbs_app.engine_reference import build_validated,check_samples,ReferenceMismatch


class EngineReferenceTests(unittest.TestCase):
    def setUp(self):
        self.reference=dict(warmup_depth=np.array([1.],np.float32),cached_new_cache_0=np.array([.876124978],np.float32))
        self.bad=dict(self.reference,cached_new_cache_0=np.array([.87822753],np.float32))

    def test_observed_cache_discrepancy_retries_only_cached_stage_without_relaxing_tolerance(self):
        compile=Mock();sample=Mock(side_effect=[self.bad,self.reference])
        attempts=build_validated(('warmup','cached'),compile,sample,self.reference,.001,'518x924')
        self.assertEqual(attempts,2)
        self.assertEqual([call.args[0] for call in compile.call_args_list],['warmup','cached','cached'])

    def test_repeated_bad_candidate_remains_failure_with_named_output(self):
        with self.assertRaises(ReferenceMismatch) as result:
            build_validated(('warmup','cached'),Mock(),Mock(return_value=self.bad),self.reference,.001,'518x924')
        self.assertIn('cached_new_cache_0',str(result.exception))
        self.assertEqual(result.exception.args[0].error_id,'E_ENGINE_REFERENCE_MISMATCH')

    def test_invalid_signature_and_nonfinite_values_are_not_retried(self):
        for invalid in ({},dict(self.reference,warmup_depth=np.array([np.nan],np.float32))):
            sample=Mock(return_value=invalid)
            with self.assertRaises(ValueError):build_validated(('warmup','cached'),Mock(),sample,self.reference,.001,'518x924')
            sample.assert_called_once()

    def test_warmup_failure_rebuilds_both_dependent_stages(self):
        compile=Mock();bad=dict(self.reference,warmup_depth=np.array([2.],np.float32))
        self.assertEqual(build_validated(('warmup','cached'),compile,Mock(side_effect=[bad,self.reference]),self.reference,.001,'profile'),2)
        self.assertEqual([call.args[0] for call in compile.call_args_list],['warmup','cached','warmup','cached'])

    def test_observed_fp16_candidate_passes_new_cache_contract_but_not_old_pointwise_guard(self):
        root=Path(__file__).resolve().parents[2]
        with np.load(root/'v1/tests/fixtures/vda-fp16-candidate-896.npz') as actual,\
             np.load(root/'models/engine-reference/vda-small-spatial-896.npz') as reference:
            samples={key:actual[key] for key in actual.files}
            with self.assertRaises(ReferenceMismatch):check_samples(samples,reference,.001,'518x896')
            check_samples(samples,reference,.001,'518x896','vda-fp16-cache-v1')

    def test_fp16_cache_guard_rejects_gain_corruption_spikes_and_changed_depth(self):
        reference={'warmup_depth':np.ones(256,np.float32),'cached_new_cache_0':np.ones(256,np.float32)}
        cases=[]
        for value in (np.zeros(256,np.float32),np.full(256,1.02,np.float32)):
            cases.append(dict(reference,cached_new_cache_0=value))
        spike=np.ones(256,np.float32);spike[0]=1.1
        cases.append(dict(reference,cached_new_cache_0=spike))
        cases.append(dict(reference,warmup_depth=np.full(256,1.01,np.float32)))
        for case in cases:
            with self.assertRaises(ReferenceMismatch):check_samples(case,reference,.001,'profile','vda-fp16-cache-v1')
