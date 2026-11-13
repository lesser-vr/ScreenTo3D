"""Fit source geometry into a validated oVDA canvas, preserving native transforms."""
CANVASES = ((518, 686), (518, 896), (518, 924))
TRIAL_CANVASES = ((392, 700),)
SUPPORTED_CANVASES = CANVASES + TRIAL_CANVASES


def validate_dimensions(width, height):
    if (type(width) is not int or type(height) is not int
            or not (16 <= width <= 4096 and 16 <= height <= 2160)):
        raise ValueError('oVDA source dimensions must be 16..4096 by 16..2160')


def native_profile(width, height):
    validate_dimensions(width, height)
    scale = max(518/width, 518/height)
    shape = (max(518, round(height*scale/14)*14), max(518, round(width*scale/14)*14))
    return shape if 1.30 <= width/height <= 1.78 and shape in CANVASES else None


def content_rect(width, height, shape):
    validate_dimensions(width, height)
    shape = tuple(shape)
    if shape not in SUPPORTED_CANVASES:
        raise ValueError('Unsupported oVDA inference canvas')
    native = native_profile(width, height)
    if native == shape:
        return 0, 0, *shape
    h, w = shape
    scale = min(w/width, h/height)
    rh, rw = max(1, round(height*scale)), max(1, round(width*scale))
    return (h-rh)//2, (w-rw)//2, rh, rw


def select_profile(width, height, available=CANVASES):
    validate_dimensions(width, height)
    choices = sorted(set(available))
    if not choices or any(shape not in SUPPORTED_CANVASES for shape in choices):
        raise ValueError('No validated oVDA inference canvas is installed')
    native = native_profile(width, height)
    if native in choices:
        return native
    def coverage(shape):
        _, _, h, w = content_rect(width, height, shape)
        return h*w/(shape[0]*shape[1])
    return max(choices, key=coverage)
