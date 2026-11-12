"""Depth and model-specific cache acceptance with bounded candidate rebuilds."""
import numpy as np
from .messages import ErrorMessage as E


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
        if cache_policy=='vda-fp16-cache-v1' and '_new_cache_' in label:
            # FP16 tactic variants can differ in intermediate activations while
            # passing the unchanged final-depth reference. Avoid near-zero
            # element-relative ratios; bound both aggregate and sparse errors.
            baseline=expected.astype(np.float64);delta=values.astype(np.float64)-baseline
            scale=max(1e-6,float(np.sqrt(np.mean(baseline**2))))
            relative_rmse=float(np.sqrt(np.mean(delta**2)))/scale
            normalized_max=float(np.abs(delta).max())/scale
            if relative_rmse<=.01 and normalized_max<=.03:continue
        raise ReferenceMismatch(profile,label,values,expected,tolerance)


def build_validated(stages,compile_stage,sample,reference,tolerance,profile,cache_policy=None):
    pending=tuple(stages)
    for attempt in (1,2):
        for stage in pending:compile_stage(stage)
        try:check_samples(sample(),reference,tolerance,profile,cache_policy)
        except ReferenceMismatch as error:
            if attempt==2:raise
            # A valid warmup need not be rebuilt for a cached-stage discrepancy.
            # Rebuilding warmup requires rebuilding its dependent cached stage too.
            pending=('cached',) if error.label.startswith('cached_') and 'cached' in stages else tuple(stages)
        else:return attempt
    raise RuntimeError('Unreachable validation state')
