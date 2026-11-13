"""Depth and model-specific cache acceptance with bounded candidate rebuilds."""
import numpy as np
from .messages import ErrorMessage as E

VDA_REFERENCE_V2='vda-fp16-reference-v2'


def _within_tensor_limits(actual,reference,relative_rmse_limit,normalized_max_limit):
    baseline=reference.astype(np.float64);delta=actual.astype(np.float64)-baseline
    scale=max(1e-6,float(np.sqrt(np.mean(baseline**2))))
    relative_rmse=float(np.sqrt(np.mean(delta**2)))/scale
    normalized_max=float(np.abs(delta).max())/scale
    return relative_rmse<=relative_rmse_limit and normalized_max<=normalized_max_limit


class ReferenceMismatch(ValueError):
    def __init__(self,profile,label,actual,reference,tolerance):
        self.label=label
        delta=np.abs(actual-reference)
        bad=delta>(tolerance+tolerance*np.abs(reference))
        super().__init__(E('E_ENGINE_REFERENCE_MISMATCH',profile=profile,tensor=label,
                           mismatched=int(bad.sum()),total=actual.size,maximum=float(delta.max())))


def check_samples(actual,reference,tolerance,profile,cache_policy=None):
    if set(actual)!=set(reference):raise ValueError(E('E_ENGINE_REFERENCE_SCHEMA',profile=profile))
    for label,values in actual.items():
        expected=reference[label]
        if values.shape!=expected.shape or not np.isfinite(values).all() or not np.isfinite(expected).all():
            raise ValueError(E('E_ENGINE_REFERENCE_SCHEMA',profile=profile))
        if np.allclose(values,expected,atol=tolerance,rtol=tolerance):continue
        if cache_policy in ('vda-fp16-cache-v1',VDA_REFERENCE_V2) and '_new_cache_' in label:
            # FP16 tactic variants can differ in intermediate activations while
            # passing the unchanged final-depth reference. Avoid near-zero
            # element-relative ratios; bound both aggregate and sparse errors.
            if _within_tensor_limits(values,expected,.01,.03):continue
        if cache_policy==VDA_REFERENCE_V2 and label in ('warmup_depth','cached_depth'):
            # Model-specific FP16 output contract, separate from the cache guard:
            # bound aggregate drift AND isolated outliers instead of allowing
            # unbounded exceptions for a small number of mismatched elements.
            if _within_tensor_limits(values,expected,.0005,.005):continue
        raise ReferenceMismatch(profile,label,values,expected,tolerance)


def build_validated(stages,compile_stage,sample,reference,tolerance,profile,cache_policy=None):
    pending=tuple(stages)
    for attempt in (1,2):
        for stage in pending:compile_stage(stage)
        try:check_samples(sample(),reference,tolerance,profile,cache_policy)
        except ReferenceMismatch as error:
            if attempt==2:raise
            # A cache-only mismatch can retry the cached stage. Final cached
            # depth also depends on warmup outputs: retry that whole pair.
            pending=('cached',) if error.label.startswith('cached_new_cache_') and 'cached' in stages else tuple(stages)
        else:return attempt
    raise RuntimeError('Unreachable validation state')
