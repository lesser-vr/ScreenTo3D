"""Measured local operating guidance, not automatic resizing or support claims."""

from .messages import Message as M

LAB_CADENCE = {
    (1280, 720): M('About 30 fps output · Recommended local starting point'),
    (1920, 1080): M('About 18 fps output · Below 30 fps'),
    (3840, 2160): M('About 3 fps output · Not recommended for live use'),
}


def guidance(width, height):
    result = LAB_CADENCE.get(
        (width, height), M('Sustained performance at this resolution is unverified · Start at 1280×720')
    )
    return M('{v0} (measured on RTX 5090 / generated SDR window). No automatic scaling.', v0=result)
