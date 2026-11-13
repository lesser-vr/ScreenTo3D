"""Pinned public default live-test corpus; personal media is never implicit."""

import hashlib
import json
import subprocess
import cv2
from screento3d_app.desktop_jobs import ROOT, BUNDLE

SOURCES = {
    "FloorballGame": "e68fce59944a9099df25dc81b145f871f2c370f21fa7b6c81e43fc7d9bceca00",
    "OfficeWalk": "f5782245401781cd358727a382a74f3e7763880cc855811a716159899cfb41a1",
    "ParkingGarage": "aabbde5730f95eb6fb681e79da9a4ea544a62e6155e1219514909b60c7451403",
}
ATTRIBUTION = (
    "UVG-VCM, Ultra Video Group, Tampere University; CC BY 4.0. "
    "T. Partanen et al., UVG-VCM: Benchmarking dataset for machine-oriented visual "
    "data compression, QoMEX 2026. https://tie-ultravideo.rd.tuni.fi/UVG-VCM/index.html "
    "; https://creativecommons.org/licenses/by/4.0/ . "
    "Modified: compressed previews, first 6 seconds, Lanczos 3840x2160 to 1920x1080, "
    "H264 CRF18, 60fps preserved; no audio added. No endorsement."
)
CORPUS = ROOT / "out/public-live-default"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    CORPUS.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, digest in SOURCES.items():
        source = ROOT / "out/public-video-source/uvg-vcm" / f"{name}.mp4"
        if sha(source) != digest:
            raise ValueError(f"Public source hash mismatch: {name}")
        target = CORPUS / f"{name}.mp4"
        record = target.with_suffix(".json")
        if target.exists():
            prior = json.loads(record.read_text())
            if prior["sha256"] != sha(target) or prior["source_sha256"] != digest:
                raise ValueError("Prepared public clip changed")
        else:
            subprocess.run(
                [
                    str(BUNDLE / "ffmpeg/ffmpeg.exe"),
                    "-v",
                    "error",
                    "-i",
                    str(source),
                    "-t",
                    "6",
                    "-an",
                    "-vf",
                    "scale=1920:1080:flags=lanczos",
                    "-c:v",
                    "libx264",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    str(target),
                ],
                check=True,
            )
            prior = dict(
                name=name,
                sha256=sha(target),
                source_sha256=digest,
                source_url=f"https://tie-ultravideo.rd.tuni.fi/UVG-VCM/{name}/{name}.mp4",
                attribution=ATTRIBUTION,
            )
            record.write_text(json.dumps(prior, indent=2))
        manifest.append(prior)
    (CORPUS / "ATTRIBUTION.txt").write_text(ATTRIBUTION)
    return manifest


class PublicFrames:
    """Decode one owned frame at a time; iteration restarts per mode."""

    def __init__(self, name, count=360):
        if name not in SOURCES or not 1 <= count <= 360:
            raise ValueError("Invalid public fixture selection")
        self.path = CORPUS / f"{name}.mp4"
        self.count = count
        record = json.loads(self.path.with_suffix(".json").read_text())
        if sha(self.path) != record["sha256"]:
            raise ValueError("Public fixture hash mismatch")

    def __iter__(self):
        capture = cv2.VideoCapture(str(self.path))
        try:
            for _ in range(self.count):
                ok, frame = capture.read()
                if not ok:
                    raise RuntimeError("Public fixture missing frame")
                yield cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        finally:
            capture.release()

    def __getitem__(self, index):
        if index < 0:
            index += self.count
        if not 0 <= index < self.count:
            raise IndexError(index)
        capture = cv2.VideoCapture(str(self.path))
        try:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError("Public fixture seek failed")
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        finally:
            capture.release()


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))
