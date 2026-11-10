"""Model-oriented UI descriptions, without loading engines or importing CUDA."""

from .messages import Message as M
from .config import DEFAULT_MODE_MODELS, MODE_MODEL_CHOICES
from .optional_models import available


def vda_precision(engine):
    from .vda_artifacts import uses_mixed_fp16
    installed = available('vda-small', engine)
    mixed = not installed or uses_mixed_fp16(engine)
    precision = M('Mixed FP16') if mixed else 'FP32'
    detail = (M('Most encoder operations use FP16; temporal processing, history, input and output remain FP32.')
              if mixed else M('The selected engine uses FP32.'))
    if not installed:
        detail += M('\nWhen not installed, precision refers to the model version that will be installed.')
    return precision, detail


def model_info(model, engine=''):
    if model == 'da2-small':
        return 'DA2 Small', 'FP16', (
            M('The default model prioritizes speed and responsiveness.\n\nModel operations use FP16; input, output and some processing use FP32.'))
    if model == 'da2-base':
        return 'DA2 Base', M('Mixed FP16'), (
            M('A larger model than DA2 Small. It costs more to process, and depth detail varies by scene.\n\nMixed FP16 and FP32 precision. Most model operations use FP16; sensitive normalization, Softmax, Resize, input and output remain FP32.'))
    if model == 'vda-small':
        precision, detail = vda_precision(engine)
        return 'VDA Small', precision, (
            M('Uses previous frames to improve temporal depth consistency. VFG is currently unavailable with live output from this model.\n\n') + detail)
    if model == 'ovda-small-c16':
        return 'oVDA c16', M('Mixed FP16'), (
            M('A separate video depth model that uses previous-frame history. Available from source only, subject to personal, non-commercial license terms.\n\nUses a 518×924 mixed-precision engine. The encoder and spatial attention use FP16; temporal processing, caches, depth output and floating-point input/output remain FP32.'))
    raise ValueError(M('Unknown depth model.'))


def selection_info(mode, model, engines):
    name, precision, description = model_info(model, engines.get(model, ''))
    if mode == 'offline-quality':
        name = M('{name} · 5-frame', name=name)
        description = (M('For file conversion only. VDA Small uses a centered five-frame context per scene, reading two frames ahead.\n\n') + vda_precision(engines.get(model, ''))[1])
    label = M('{name} · {precision} · Default', name=name, precision=precision) if mode == 'performance' else M('{name} · {precision}', name=name, precision=precision)
    return dict(key=f'{mode}/{model}', mode=mode, model=model, label=label, help=description)


def selection_choices(modes, engines, *, portable):
    return [selection_info(mode, model, engines)
            for mode in modes for model in sorted(MODE_MODEL_CHOICES[mode], key=lambda m: m != DEFAULT_MODE_MODELS[mode])
            if not (portable and model == 'ovda-small-c16')]
