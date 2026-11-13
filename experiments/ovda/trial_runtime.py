# oVDA derivative experiment, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Explicit process-local trial allowlist; no production loader/default changes."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from screento3d_app import ovda
from screento3d_app.desktop_jobs import ROOT

TRIAL = ROOT/'out/ovda-precision-20261109'
PINS = {
    'encoder': ('d4b242984e6e1dc63a6857462954bb71e699a482d6af3dbd79531279762b41b3', 92111580),
    'encoder-spatial': ('394894301beee2302decaf43e7dd4912c043cae469a07f19f4848774a5eb0ec1', 91370692),
}
CONTROL = ('7bd4916e0104a1306c99dd0bb5a37e8bf27aed0f8ac698b5f35f1076147b0e75',129355452)
LOW_TRIAL=ROOT/'out/ovda-resolution-20261109'
LOW_PINS={
    'low-fp32':('ac135d0bb63159ec0c98b1ea5f2907a8b1105161a682aa1b333d352eaad2f184',126550868),
    'low-fp16':('1c4891befbded49c103730bcbf8d60ef7ac01547df3b6dcb876e5fa1b55cc6d8',86803228),
}
RUNTIME=Path('C:/TensorRT/TensorRT-11.2.1.2/bin')


def runtime_label(variant):
    return 'tensorrt-mixed-fp16-trial' if variant in (*PINS,'low-fp16') else 'tensorrt-fp32-trial'


def live_trial_worker(variant,*args,**kwargs):
    if kwargs.get('backend_snapshot',{}).get('model')!='ovda-small-c16':
        raise ValueError('이 시험 실행기에서는 oVDA를 선택하세요.')
    kwargs['gpu_capture_snapshot']=True
    return trial_sbs_worker(variant,*args,**kwargs)


@contextmanager
def selected(variant):
    if variant == 'fp32':
        with patch.object(ovda,'PROFILES',{(518,924):('6aab5d663f544192b78a7c16d8e86c2345774602c92f93c8c1bd02376e3d410a',129402708)}):
            yield ROOT/'out/ovda-local/518x924-fp32'
    elif variant in LOW_PINS:
        with patch.object(ovda,'PROFILES',{(392,700):LOW_PINS[variant]}):
            directory=LOW_TRIAL/('low-fp32' if variant=='low-fp32' else 'mixed/encoder-spatial')
            ovda.checked_plan(directory,(392,700))
            yield directory
    elif variant in PINS or variant=='fp32-current':
        pin=CONTROL if variant=='fp32-current' else PINS[variant]
        with patch.object(ovda,'PROFILES',{(518,924):pin}):
            # The unchanged loader verifies the explicitly pinned bytes before use.
            directory=(ROOT/'out/ovda-precision-control-20261109'/variant if variant=='fp32-current' else TRIAL/variant)
            ovda.checked_plan(directory,(518,924))
            yield directory
    else:
        raise ValueError('Unknown precision trial')


def create_engine(variant):
    with selected(variant) as directory:
        engine=ovda.runtime_class(True)(directory=directory,runtime_dir=RUNTIME,
                                        profile=(392,700) if variant in LOW_PINS else (518,924))
        engine.runtime_label=runtime_label(variant)
    return engine


def trial_sbs_worker(variant, *args, **kwargs):
    from screento3d_app.live_sbs import sbs_worker
    with selected(variant) as directory:
        kwargs['backend_snapshot']=dict(kwargs['backend_snapshot'],engine=str(directory))
        original=ovda.binding
        def trial_binding(*values,**options):
            binding=original(*values,**options)
            def factory(progress):
                engine=binding.engine_factory(progress);engine.runtime_label=runtime_label(variant)
                return engine
            return replace(binding,spec=replace(binding.spec,runtime=runtime_label(variant)),engine_factory=factory)
        with patch.object(ovda,'binding',trial_binding):
            return sbs_worker(*args, **kwargs)
