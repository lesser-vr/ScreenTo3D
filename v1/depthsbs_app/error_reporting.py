"""Default worker errors omit arbitrary exception text; private detail is opt-in."""
from .messages import Message, payload

def error_event(error, *, detailed=False):
    text = str(error)
    categories = (
        ('H.264 Full SBS output width', 'output_geometry', Message('The selected codec cannot preserve this Full SBS width. For 4K input, explicitly select HEVC.')),
        ('HEVC Full SBS output width', 'output_geometry', Message('Full SBS width exceeds the validated HEVC profile. Check source dimensions.')),
        ('Decode', 'decode', Message('Video decoding failed. Check that the input plays correctly.')),
        ('Decoder', 'decode', Message('Video decoding failed. Check that the input plays correctly.')),
        ('NVENC', 'encode', Message('Video encoding failed. Check the selected codec and GPU support.')),
        ('Audio mux', 'mux', Message('Audio finalization failed. Check the input audio and destination.')),
        ('Mux produced', 'mux', Message('No final media was produced. The previous output was preserved.')),
        ('Input and output', 'paths', Message('Input and output must be different files.')),
        ('Cancel marker', 'paths', Message('The cancellation marker must be separate from media files.')),
        ('TensorRT', 'backend', Message('Depth runtime failed. Check the selected model and validated runtime.')),
        ('Depth model', 'backend', Message('The selected depth model is missing. Check the model installation.')),
        ('CUDA', 'gpu', Message('GPU processing failed. Stop the job and restart its session.')),
    )
    code, message = 'conversion', Message('Conversion failed. Check input, output access and selected model. Explicit detailed errors can provide private diagnostics.')
    for prefix, candidate, guidance in categories:
        if text.startswith(prefix):
            code, message = candidate, guidance
            break
    event = dict(event='error', type=type(error).__name__, code=code, message=message,
                 cleanup_failed=bool(getattr(error, '__notes__', None)))
    if detailed:
        event.update(message=text, notes=getattr(error, '__notes__', []))
    else:
        event['localized'] = payload(message)
    return event
