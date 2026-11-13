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

    def test_report_shaped_sparse_depth_rounding_needs_explicit_v2_contract(self):
        # Reconstruct the reported 2/256, 0.0066 error pattern, not the user's
        # unavailable exact tensors. Values come from our pinned random-input probe.
        root=Path(__file__).resolve().parents[2]
        with np.load(root/'models/engine-reference/vda-small-spatial-896.npz') as stored:
            reference={key:stored[key] for key in ('warmup_depth','cached_depth')}
        actual={key:value.copy() for key,value in reference.items()}
        actual['cached_depth'][np.argsort(reference['cached_depth'])[:2]]+=np.float32(.0066)
        for policy in (None,'vda-fp16-cache-v1'):
            with self.assertRaises(ReferenceMismatch) as error:
                check_samples(actual,reference,.001,'518x896',policy)
            self.assertEqual(error.exception.args[0].values['mismatched'],2)
        check_samples(actual,reference,.001,'518x896','vda-fp16-reference-v2')

    def test_v2_depth_limits_reject_bias_sparse_outlier_and_nonfinite_values(self):
        reference={key:np.full(256,5.,np.float32) for key in ('warmup_depth','cached_depth')}
        cases=[]
        cases.append(dict(reference,cached_depth=np.full(256,5.01,np.float32)))
        spike=reference['cached_depth'].copy();spike[0]+=.03
        cases.append(dict(reference,cached_depth=spike))
        cases.append(dict(reference,cached_depth=np.zeros(256,np.float32)))
        for invalid in (np.nan,np.inf):
            values=reference['cached_depth'].copy();values[0]=invalid
            cases.append(dict(reference,cached_depth=values))
        for actual in cases:
            with self.assertRaises(ValueError):
                check_samples(actual,reference,.001,'profile','vda-fp16-reference-v2')

    def test_v2_preserves_the_existing_intermediate_cache_limits(self):
        root=Path(__file__).resolve().parents[2]
        with np.load(root/'v1/tests/fixtures/vda-fp16-candidate-896.npz') as actual,\
             np.load(root/'models/engine-reference/vda-small-spatial-896.npz') as reference:
            check_samples({key:actual[key] for key in actual.files},reference,.001,'profile','vda-fp16-reference-v2')
        reference={'warmup_depth':np.ones(256,np.float32),'cached_new_cache_0':np.ones(256,np.float32)}
        with self.assertRaises(ReferenceMismatch):
            check_samples(dict(reference,cached_new_cache_0=np.full(256,1.02,np.float32)),
                          reference,.001,'profile','vda-fp16-reference-v2')

    def test_cached_depth_failure_rebuilds_its_warmup_dependency(self):
        reference={'warmup_depth':np.ones(256,np.float32),'cached_depth':np.ones(256,np.float32)}
        bad=dict(reference,cached_depth=np.full(256,1.01,np.float32));compile=Mock()
        attempts=build_validated(('warmup','cached'),compile,Mock(side_effect=[bad,reference]),
                                 reference,.001,'profile','vda-fp16-reference-v2')
        self.assertEqual(attempts,2)
        self.assertEqual([call.args[0] for call in compile.call_args_list],['warmup','cached','warmup','cached'])
