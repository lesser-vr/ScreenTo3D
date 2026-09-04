import json
import os
import subprocess
import time
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .config import MODES, ModePolicy
from .resources import resource_path
from .trt_backend import DepthEngine
from .telemetry import StageMetrics
from .lifecycle import Lifecycle


Progress = Callable[[dict], None]
MEAN = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)[:, None, None]
STD = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)[:, None, None]


def _tool(name: str) -> str:
    bundled = resource_path(f"ffmpeg/{name}.exe")
    return str(bundled) if bundled.exists() else name


def _run(arguments: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        arguments, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def probe_video(path: Path) -> dict:
    result = _run([
        _tool("ffprobe"), "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(path),
    ])
    if result.returncode != 0:
        raise RuntimeError("FFprobe failed: " + result.stderr.strip())
    payload = json.loads(result.stdout)
    videos = [stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"]
    if not videos:
        raise ValueError("Input contains no video stream")
    video = videos[0]
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    if width < 16 or height < 16 or width > 7680 or height > 4320:
        raise ValueError(f"Unsupported video dimensions: {width}x{height}")
    rate_text = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
    numerator, denominator = (int(value) for value in rate_text.split("/"))
    fps = numerator / denominator if denominator else 0.0
    if fps <= 0.0 or fps > 240.0:
        raise ValueError(f"Unsupported frame rate: {rate_text}")
    duration = float(video.get("duration") or payload.get("format", {}).get("duration") or 0.0)
    return {
        "width": width, "height": height, "fps": fps, "fps_text": rate_text,
        "duration": duration,
        "total_frames": int(video.get("nb_frames") or round(duration * fps)),
        "codec": video.get("codec_name", "unknown"),
        "has_audio": any(stream.get("codec_type") == "audio" for stream in payload.get("streams", [])),
    }


def preprocess(frame: np.ndarray) -> np.ndarray:
    resized = cv2.resize(frame, (518, 518), interpolation=cv2.INTER_CUBIC)
    rgb = resized.astype(np.float32).transpose(2, 0, 1) / 255.0
    return ((rgb - MEAN) / STD)[None, ...]


class StereoSynthesizer:
    def __init__(self, width: int, height: int, policy: ModePolicy):
        self.width, self.height, self.policy = width, height, policy
        self.grid_x, self.grid_y = np.meshgrid(
            np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32)
        )
        self.smoothed_depth = self.low = self.high = None

    def render(self, frame: np.ndarray, depth: np.ndarray) -> np.ndarray:
        resized = cv2.resize(depth[0], (self.width, self.height), interpolation=cv2.INTER_CUBIC)
        low, high = float(np.percentile(resized, 2.0)), float(np.percentile(resized, 98.0))
        alpha = self.policy.temporal_alpha
        self.low = low if self.low is None else alpha * low + (1.0 - alpha) * self.low
        self.high = high if self.high is None else alpha * high + (1.0 - alpha) * self.high
        normalized = np.clip((resized - self.low) / max(self.high - self.low, 1.0e-6), 0.0, 1.0)
        self.smoothed_depth = normalized if self.smoothed_depth is None else (
            alpha * normalized + (1.0 - alpha) * self.smoothed_depth
        )
        disparity = (self.smoothed_depth - self.policy.convergence) * max(
            1.0, self.width * self.policy.divergence
        )
        left = cv2.remap(
            frame, self.grid_x + disparity * 0.5, self.grid_y,
            cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT101,
        )
        right = cv2.remap(
            frame, self.grid_x - disparity * 0.5, self.grid_y,
            cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT101,
        )
        return np.concatenate((left, right), axis=1)


def _read_frame(stream, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            break
        chunks.extend(chunk)
    return bytes(chunks)


def convert_video(
    input_path: Path, output_path: Path, mode: str, progress: Progress,
    cancel_path: Path | None = None,
) -> dict:
    job_started = time.perf_counter()
    input_path, output_path = input_path.resolve(), output_path.resolve()
    if input_path == output_path:
        raise ValueError("Input and output paths must differ")
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}")
    probe_started = time.perf_counter()
    policy, metadata = MODES[mode], probe_video(input_path)
    probe_seconds = time.perf_counter() - probe_started
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = output_path.with_suffix(output_path.suffix + ".partial.mp4")
    video_path = output_path.with_suffix(output_path.suffix + ".video-only.mp4")
    partial_path.unlink(missing_ok=True)
    video_path.unlink(missing_ok=True)
    width, height = metadata["width"], metadata["height"]
    decode = encode = None
    started, frames, last_depth = time.perf_counter(), 0, None
    metrics = StageMetrics()
    decoded_pipe_bytes = encoded_pipe_bytes = 0
    lifecycle = Lifecycle()
    try:
        progress({"event": "start", "mode": mode, "metadata": metadata})
        with DepthEngine(progress) as engine:
            lifecycle.checkpoint('engine_startup')
            decode = subprocess.Popen(
                [_tool("ffmpeg"), "-v", "error", "-i", str(input_path),
                 "-map", "0:v:0", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            encode = subprocess.Popen(
                [_tool("ffmpeg"), "-y", "-v", "error", "-f", "rawvideo",
                 "-pix_fmt", "rgb24", "-s", f"{width * 2}x{height}",
                 "-r", f"{metadata['fps']:.8f}", "-i", "pipe:0", "-an",
                 "-c:v", "h264_nvenc", "-preset", policy.nvenc_preset,
                 "-tune", "hq", "-rc", "vbr", "-cq", str(policy.cq),
                 "-b:v", "0", "-pix_fmt", "yuv420p", str(video_path)],
                stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            synthesizer, frame_size = StereoSynthesizer(width, height, policy), width * height * 3
            lifecycle.checkpoint('pipeline_setup')
            while True:
                if cancel_path is not None and cancel_path.exists():
                    raise InterruptedError("Conversion cancelled")
                frame_started = time.perf_counter()
                read_started = time.perf_counter()
                raw = _read_frame(decode.stdout, frame_size)
                if not raw:
                    break
                if len(raw) != frame_size:
                    raise RuntimeError("Decoder returned a truncated frame")
                frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
                decoded_pipe_bytes += len(raw)
                metrics.observe('decode_read', time.perf_counter() - read_started)
                if last_depth is None or frames % policy.inference_cadence == 0:
                    with metrics.measure('preprocess'):
                        tensor = preprocess(frame)
                    with metrics.measure('depth_inference'):
                        last_depth = engine.infer(tensor)
                with metrics.measure('temporal_stereo'):
                    rendered = synthesizer.render(frame, last_depth).tobytes()
                with metrics.measure('encode_write'):
                    written = encode.stdin.write(rendered)
                    if written != len(rendered):
                        raise RuntimeError('Encoder pipe returned a short write')
                    encoded_pipe_bytes += written
                metrics.observe('frame_total', time.perf_counter() - frame_started)
                frames += 1
                if frames == 1 or frames % 10 == 0:
                    total = metadata["total_frames"]
                    progress({
                        "event": "progress", "frame": frames, "total_frames": total,
                        "percent": min(100.0, frames * 100.0 / total) if total else None,
                    })
            lifecycle.checkpoint('frame_loop')
            decode.stdout.close()
            decode_error = decode.stderr.read().decode("utf-8", "replace")
            if decode.wait() != 0:
                raise RuntimeError("Decode failed: " + decode_error.strip())
            lifecycle.checkpoint('decode_drain')
            encode.stdin.close()
            encode_error = encode.stderr.read().decode("utf-8", "replace")
            if encode.wait() != 0:
                raise RuntimeError("NVENC encode failed: " + encode_error.strip())
            lifecycle.checkpoint('encode_drain')
            resource_stats = engine.telemetry()
            lifecycle.checkpoint('resource_snapshot')
        lifecycle.checkpoint('backend_close')
        if frames == 0:
            raise RuntimeError("No video frames were decoded")
        mux = _run([
            _tool("ffmpeg"), "-y", "-v", "error", "-i", str(video_path),
            "-i", str(input_path), "-map", "0:v:0", "-map", "1:a?",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
            "-movflags", "+faststart", str(partial_path),
        ])
        if mux.returncode != 0:
            raise RuntimeError("Audio mux failed: " + mux.stderr.strip())
        lifecycle.checkpoint('audio_mux')
        output_path.unlink(missing_ok=True)
        partial_path.replace(output_path)
        lifecycle.checkpoint('publish')
        elapsed = time.perf_counter() - started
        result = {
            "event": "complete", "output": str(output_path), "frames": frames,
            "elapsed_seconds": elapsed, "processing_fps": frames / elapsed,
            "mode": mode, "policy": policy.__dict__,
        }
        result['telemetry'] = {
            'schema_version': 2, 'sample_capacity': metrics.capacity,
            'percentile_scope': 'trailing_window', 'stages': metrics.summary(),
            'resources': resource_stats,
            'host_pipe_payload_bytes': {
                'decoded_rgb': decoded_pipe_bytes, 'encoded_sbs_rgb': encoded_pipe_bytes,
            },
            'scheduling_contract': {
                'worker_active_frame_limit': 1, 'application_work_queue_capacity': 0,
                'external_buffering_measured': False,
            },
            'zero_copy': False,
            'lifecycle_seconds': dict(lifecycle.seconds),
            'probe_seconds': probe_seconds,
            'job_elapsed_seconds': time.perf_counter() - job_started,
        }
        progress(result)
        return result
    except InterruptedError:
        progress({"event": "cancelled", "frames": frames})
        raise
    except BaseException:
        raise
    finally:
        for process in (decode, encode):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
        partial_path.unlink(missing_ok=True)
        video_path.unlink(missing_ok=True)
        if cancel_path is not None:
            cancel_path.unlink(missing_ok=True)
