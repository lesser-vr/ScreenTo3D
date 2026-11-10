"""Explicit-process registration only. Normal app never imports this module."""
from contextlib import contextmanager
from pathlib import Path
from runtime import ARTIFACTS, Engine, check_plan, rect

@contextmanager
def installed():
    from depthsbs_app import config, live_backend, live_model, live_preview, desktop
    from depthsbs_app.depth_backend import BackendBinding, BackendSpec
    old_choices = config.MODE_MODEL_CHOICES['performance']
    old_default = config.DEFAULT_MODE_MODELS['performance']
    old_binding, old_native, old_create = live_backend.binding, live_preview.NATIVE_MODELS, desktop.create_app
    check_plan()

    def binding(snapshot, mode, metadata, *args):
        if snapshot['model'] != 'zipdepth-base':
            return old_binding(snapshot,mode,metadata,*args)
        live_backend.validate_snapshot(snapshot,mode)
        if Path(snapshot['engine']).resolve() != ARTIFACTS.resolve():
            raise ValueError('Unexpected ZipDepth artifact directory')
        rect(metadata['width'],metadata['height'])
        return BackendBinding(BackendSpec('zipdepth-base','tensorrt-fp16'),Engine,lambda frame:frame)

    def create_app():
        result = old_create()
        result[2].engine_paths['zipdepth-base'] = str(ARTIFACTS)
        return result

    try:
        config.MODE_MODEL_CHOICES['performance'] = ('zipdepth-base',)
        config.DEFAULT_MODE_MODELS['performance'] = 'zipdepth-base'
        desktop.MODELS['zipdepth-base'] = ('ZipDepth Base (실험)', 'zipdepth-exact-20261106', '', '로컬 실험 · 배포 범위 미확정')
        live_model._MODELS['zipdepth-base'] = live_model.LiveModelAdapter(
            live_model._source_renderer,live_model._source_host_io,gpu_capture=True,coalesced_history=True)
        live_backend.binding = binding
        live_preview.NATIVE_MODELS = (*old_native,'zipdepth-base')
        desktop.create_app = create_app
        yield
    finally:
        config.MODE_MODEL_CHOICES['performance'] = old_choices
        config.DEFAULT_MODE_MODELS['performance'] = old_default
        live_model._MODELS.pop('zipdepth-base',None)
        desktop.MODELS.pop('zipdepth-base',None)
        live_backend.binding,live_preview.NATIVE_MODELS,desktop.create_app = old_binding,old_native,old_create

def worker(*args,**kwargs):
    from depthsbs_app.live_sbs import sbs_worker
    with installed():
        return sbs_worker(*args,**kwargs)
