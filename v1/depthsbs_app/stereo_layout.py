"""Stereo packing contract shared by live, file and diagnostic paths."""
LAYOUTS = {
    "full-sbs": "Full SBS",
    "half-sbs": "Half SBS",
    "full-tb": "Full Top-and-Bottom",
    "half-tb": "Half Top-and-Bottom",
}


def dimensions(width, height, layout="full-sbs"):
    if layout not in LAYOUTS:
        raise ValueError(f"Unknown stereo layout: {layout}")
    eye_width = (width + 1) // 2 if layout == "half-sbs" else width
    eye_height = (height + 1) // 2 if layout == "half-tb" else height
    return ((eye_width * 2, eye_height) if layout.endswith("sbs")
            else (eye_width, eye_height * 2))


def pack(frame, layout="full-sbs"):
    """Pack full SBS RGB/BGRA; average pairs, replicating an odd final edge."""
    import numpy as np
    dimensions(frame.shape[1] // 2, frame.shape[0], layout)
    if layout == "full-sbs":
        return frame
    eyes = np.split(frame, 2, axis=1)
    axis = 1 if layout == "half-sbs" else 0
    if layout.startswith("half"):
        reduced = []
        for eye in eyes:
            if eye.shape[axis] % 2:
                pads = [(0, 0)] * eye.ndim
                pads[axis] = (0, 1)
                eye = np.pad(eye, pads, mode="edge")
            first = eye[:, ::2] if axis == 1 else eye[::2]
            second = eye[:, 1::2] if axis == 1 else eye[1::2]
            first = first.astype(np.uint16)
            reduced.append(((first + second + 1) // 2).astype(np.uint8))
        eyes = reduced
    return np.concatenate(eyes, axis=1 if layout.endswith("sbs") else 0)
