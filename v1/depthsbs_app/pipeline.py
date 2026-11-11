import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import replace
from contextlib import ExitStack
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .config import MODES, OUTPUTS, ModePolicy
from .resources import resource_path
from .depth_backend import resolve_backend
from .offline_depth import is_scene_cut as is_offline_scene_cut
from .telemetry import StageMetrics
from .lifecycle import Lifecycle
from .stereo import project_eye, guide_depth, refine_flat_background, color_change
from .messages import ErrorMessage as E


Progress = Callable[[dict], None]


def DepthEngine(progress=None):
    # Load DA2 platform dependencies only when its binding is actually selected.
    from .trt_backend import DepthEngine as TensorRTDepthEngine
    return TensorRTDepthEngine(progress)

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


def probe_video(path: Path, output_codec='h264', stereo_layout='full-sbs') -> dict:
    if output_codec not in OUTPUTS:
        raise ValueError(f'Unknown output codec: {output_codec}')
    output_policy = OUTPUTS[output_codec]
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
    from .stereo_layout import dimensions, LAYOUTS
    packed_width, packed_height = dimensions(width, height, stereo_layout)
    if packed_width % 2 or packed_height % 2:
        raise ValueError("Selected stereo layout requires even encoded width and height for YUV420.")
    if packed_width > output_policy.max_sbs_width or packed_height > output_policy.max_sbs_width:
        raise ValueError(
            f'{output_policy.name} {LAYOUTS[stereo_layout]} output {packed_width}x{packed_height} exceeds '
            f'this release limit of {output_policy.max_sbs_width} pixels per axis. '
            'Select HEVC or a Half stereo layout explicitly.'
        )
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


def _paths_alias(left, right):
    left, right = Path(left), Path(right)
    if left.resolve() == right.resolve():
        return True
    return left.exists() and right.exists() and left.samefile(right)


def preprocess(frame: np.ndarray) -> np.ndarray:
    resized = cv2.resize(frame, (518, 518), interpolation=cv2.INTER_CUBIC)
    rgb = resized.astype(np.float32).transpose(2, 0, 1) / 255.0
    return ((rgb - MEAN) / STD)[None, ...]


def depth_refresh_reason(frame, inferred_frame, index, policy, cut):
    if inferred_frame is None:
        return 'initial'
    if index % policy.inference_cadence == 0:
        return 'cadence'
    if cut:
        return 'cut'
    difference = color_change(frame, inferred_frame)
    changed = difference > policy.motion_refresh_color_threshold
    if np.mean(changed) >= policy.motion_refresh_fraction:
        return 'motion'
    if policy.local_motion_window > 0:
        local_changed = (difference > policy.local_motion_color_threshold).astype(np.uint8)
        density = float(np.mean(local_changed))
        if density > 0:
            window = policy.local_motion_window
            local_density = cv2.boxFilter(local_changed, cv2.CV_32F, (window, window),
                                         normalize=True, borderType=cv2.BORDER_CONSTANT)
            required = max(policy.local_motion_fraction, density * policy.local_motion_concentration)
            if float(np.max(local_density)) >= required:
                return 'local_motion'
    return 'reuse'


class StereoSynthesizer:
    def __init__(self, width: int, height: int, policy: ModePolicy, projection=None, *, paired_projection=None):
        self.width, self.height, self.policy = width, height, policy
        self.smoothed_depth = self.low = self.high = None
        self.previous_frame = None
        self.flat_background_frames = 0
        self.padding = None
        self.source_ns = None
        self.range_tracker = None
        if policy.stabilize_depth_range:
            from .depth_range import DepthRangeTracker
            self.range_tracker = DepthRangeTracker()
        if policy.letterbox_refinement:
            from .padding import PaddingRefiner
            self.padding = PaddingRefiner(policy.letterbox_stable_frames)
        self.project_eye = projection.project if projection is not None else project_eye
        self.project_pair = paired_projection

    def is_scene_cut(self, frame):
        if self.previous_frame is None:
            return False
        current = cv2.resize(frame, (32, 32)).astype(np.float32)
        previous = cv2.resize(self.previous_frame, (32, 32)).astype(np.float32)
        return float(np.mean(np.abs(current - previous))) / 255.0 > self.policy.scene_cut_threshold

    def render(self, frame: np.ndarray, depth: np.ndarray) -> np.ndarray:
        if self.is_scene_cut(frame):
            if self.padding is not None:
                self.padding.reset()
            self.smoothed_depth = self.low = self.high = None
            self.previous_frame = None
        resized = cv2.resize(depth[0], (self.width, self.height), interpolation=cv2.INTER_CUBIC)
        low, high = map(float, np.percentile(resized, [2.0, 98.0]).astype(resized.dtype))
        alpha = self.policy.temporal_alpha
        if self.range_tracker is not None:
            self.low,self.high=self.range_tracker.update(resized,frame,self.previous_frame,(low,high),
                self.source_ns,reset=self.low is None)
            if self.range_tracker.reset_applied:
                self.smoothed_depth=None
                self.previous_frame=None
        else:
            self.low = low if self.low is None else alpha * low + (1.0 - alpha) * self.low
            self.high = high if self.high is None else alpha * high + (1.0 - alpha) * self.high
        normalized = np.clip((resized - self.low) / max(self.high - self.low, 1.0e-6), 0.0, 1.0)
        if self.smoothed_depth is not None and self.previous_frame is not None:
            pixel_alpha = self.policy.temporal_depth_alpha if self.policy.temporal_depth_alpha is not None else alpha
            changed = color_change(frame, self.previous_frame)
            changed = cv2.dilate((changed > self.policy.temporal_color_threshold).astype(np.uint8), np.ones((7, 7), np.uint8)) != 0
            changed |= np.abs(normalized - self.smoothed_depth) > self.policy.temporal_depth_threshold
            if self.policy.temporal_depth_transition > 0:
                from .temporal_blend import blend_depth
                normalized = blend_depth(normalized, self.smoothed_depth, changed, pixel_alpha,
                    self.policy.temporal_depth_threshold, self.policy.temporal_depth_transition)
            else:
                normalized = np.where(changed, normalized, pixel_alpha * normalized + (1.0 - pixel_alpha) * self.smoothed_depth)
        self.smoothed_depth = normalized
        self.previous_frame = frame.copy()
        aligned = guide_depth(frame, normalized, radius=self.policy.depth_guide_radius)
        if self.policy.flat_background_refinement:
            refine = self.padding.refine if self.padding is not None else refine_flat_background
            refined = refine(frame, aligned,
                tolerance=self.policy.flat_background_tolerance,
                minimum_coverage=self.policy.flat_background_min_coverage,
                radius=self.policy.depth_guide_radius)
            if refined is not aligned:
                self.flat_background_frames += 1
            aligned = refined
        disparity = (aligned - self.policy.convergence) * max(
            1.0, self.width * self.policy.divergence
        )
        if self.project_pair is not None:
            left, right = self.project_pair(frame, aligned, disparity * 0.5,
                conservative_coverage=self.policy.conservative_stereo_coverage)
        else:
            # Forward splatting uses destination x = source x + shift. Near
            # inverse depth must move right in the LEFT eye (crossed disparity).
            left = self.project_eye(frame, aligned, disparity * 0.5,
                               conservative_coverage=self.policy.conservative_stereo_coverage)
            right = self.project_eye(frame, aligned, -disparity * 0.5,
                                conservative_coverage=self.policy.conservative_stereo_coverage)
        result = np.concatenate((left, right), axis=1)
        return self.padding.restore(result, frame) if self.padding is not None else result


def _read_frame(stream, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            break
        chunks.extend(chunk)
    return bytes(chunks)


def _check_cancel(cancel_path):
    if cancel_path is not None and cancel_path.exists():
        raise InterruptedError('Conversion cancelled')


def _cleanup_processes(processes):
    errors = []
    for process in processes:
        if process is None:
            continue
        try:
            if process.poll() is None:
                process.kill()
            process.wait()
        except Exception as error:
            errors.append(error)
        for name in ('stdin', 'stdout', 'stderr'):
            stream = getattr(process, name, None)
            if stream is not None:
                try:
                    stream.close()
                except Exception as error:
                    errors.append(error)
    return errors


def convert_video(
    input_path: Path, output_path: Path, mode: str, progress: Progress,
    cancel_path: Path | None = None,
    *, projection_factory=None, diagnostic_hashes=False, output_codec='h264', depth_backend=None,
    letterbox_refinement=False,
    stereo_layout="full-sbs",
    depth_strength=1.0,vfg=False,interpolation_factory=None,
) -> dict:
    job_started = time.perf_counter()
    import hashlib
    hashes = {name: hashlib.sha256() for name in ('decoded_rgb', 'depth', 'sbs_rgb')} if diagnostic_hashes else None
    input_path, output_path = input_path.resolve(), output_path.resolve()
    if _paths_alias(input_path, output_path):
        raise ValueError("Input and output paths must differ")
    if cancel_path is not None and any(_paths_alias(cancel_path, path) for path in (input_path, output_path)):
        raise ValueError("Cancel marker must differ from input and output paths")
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}")
    probe_started = time.perf_counter()
    if type(letterbox_refinement) is not bool:
        raise ValueError('letterbox_refinement must be boolean')
    import math
    if isinstance(depth_strength,bool) or not isinstance(depth_strength,(int,float)) or not math.isfinite(depth_strength) or not .25<=depth_strength<=2:
        raise ValueError(E('E_DEPTH_STRENGTH_INVALID'))
    if type(vfg) is not bool:raise ValueError(E('E_FILE_VFG_SELECTION'))
    policy = replace(MODES[mode], letterbox_refinement=letterbox_refinement, stereo_layout=stereo_layout)
    policy = replace(policy,divergence=policy.divergence*depth_strength)
    from .stereo_layout import dimensions, pack
    metadata = probe_video(input_path, output_codec=output_codec, stereo_layout=stereo_layout)
    backend = depth_backend if depth_backend is not None else resolve_backend(policy.depth_backend, DepthEngine, preprocess)
    backend.validate_policy(policy)
    offline_factory = backend.offline_processor_factory
    if mode == 'offline-quality' and offline_factory is None:
        raise ValueError('Offline Quality requires a dedicated future-aware depth processor')
    if mode != 'offline-quality' and offline_factory is not None:
        raise ValueError('Offline depth processing is file-only and requires Offline Quality mode')
    if backend.input_validator is not None:
        backend.input_validator(metadata)
    output_policy = OUTPUTS[output_codec]
    probe_seconds = time.perf_counter() - probe_started
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Per-job siblings cannot overwrite stale artifacts or a similarly named input.
    token = uuid.uuid4().hex
    partial_path = output_path.with_name(f".{output_path.name}.{token}.partial.mp4")
    video_path = output_path.with_name(f".{output_path.name}.{token}.video-only.mp4")
    width, height = metadata["width"], metadata["height"]
    packed_width, packed_height = dimensions(width, height, stereo_layout)
    output_fps=metadata['fps']*(2 if vfg else 1)
    output_total=(metadata['total_frames'] or 0)*(2 if vfg else 1)
    decode = encode = None
    started, frames, decoded_frames, last_depth = time.perf_counter(), 0, 0, None
    metrics = StageMetrics()
    decoded_pipe_bytes = encoded_pipe_bytes = 0
    scene_cut_resets = extra_cut_inferences = extra_motion_inferences = 0
    local_motion_inferences = 0
    inferred_frame = None
    offline_window = None
    lifecycle = Lifecycle()
    try:
        _check_cancel(cancel_path)
        progress({"event": "start", "mode": mode, "metadata": metadata})
        with backend.engine_factory(progress) as engine, ExitStack() as projection_scope:
            backend.reset(engine, 'start')
            lifecycle.checkpoint('engine_startup')
            interpolator=vfg_session=None
            if vfg:
                from .file_interpolation import DoubleRate
                if interpolation_factory is None:
                    from .file_vfg import FileVfg
                    interpolation_factory=FileVfg
                vfg_session=projection_scope.enter_context(interpolation_factory(width*2,height))
                interpolator=DoubleRate(vfg_session.generate)
                progress(dict(event='file_vfg',enabled=True,multiplier=2,output_fps=output_fps))
            decode = subprocess.Popen(
                [_tool("ffmpeg"), "-v", "error", "-i", str(input_path),
                 "-map", "0:v:0", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            encode = subprocess.Popen(
                [_tool("ffmpeg"), "-y", "-v", "error", "-f", "rawvideo",
                 "-pix_fmt", "rgb24", "-s", f"{packed_width}x{packed_height}",
                 "-r", f"{output_fps:.8f}", "-i", "pipe:0", "-an",
                 "-c:v", output_policy.encoder, "-tag:v", output_policy.tag,
                 "-preset", policy.nvenc_preset,
                 "-tune", "hq", "-rc", "vbr", "-cq", str(policy.cq),
                 "-b:v", "0", "-pix_fmt", "yuv420p", str(video_path)],
                stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            projection = projection_scope.enter_context(projection_factory(width, height)) if projection_factory else None
            synthesizer, frame_size = StereoSynthesizer(width, height, policy, projection), width * height * 3
            offline_window = offline_factory() if offline_factory is not None else None
            if offline_window is not None:
                progress({
                    'event': 'offline_depth',
                    'strategy': offline_window.strategy,
                    'window_frames': offline_window.capacity,
                    'lookahead_frames': offline_window.radius,
                    'bounded': True,
                })

            def write_stereo(stereo):
                nonlocal encoded_pipe_bytes, frames
                _check_cancel(cancel_path)
                with metrics.measure('stereo_pack'):
                    rendered=pack(stereo,stereo_layout).tobytes()
                if hashes is not None:
                    hashes['sbs_rgb'].update(rendered)
                with metrics.measure('encode_write'):
                    written = encode.stdin.write(rendered)
                    if written != len(rendered):
                        raise RuntimeError('Encoder pipe returned a short write')
                    encoded_pipe_bytes += written
                frames += 1
                if frames == 1 or frames % 10 == 0:
                    total = output_total
                    progress({
                        'event': 'progress', 'frame': frames, 'total_frames': total,
                        'percent': min(100.0, frames * 100.0 / total) if total else None,
                    })

            def write_sample(output_frame,output_depth):
                cut=synthesizer.is_scene_cut(output_frame) if interpolator is not None else False
                with metrics.measure('temporal_stereo'):
                    stereo=synthesizer.render(output_frame,output_depth)
                if hashes is not None:hashes['depth'].update(output_depth.tobytes())
                if interpolator is None:samples=(stereo,)
                else:
                    _check_cancel(cancel_path)
                    with metrics.measure('frame_interpolation'):
                        samples=interpolator.submit(stereo,cut_before=cut)
                for sample in samples:write_stereo(sample)

            lifecycle.checkpoint('pipeline_setup')
            while True:
                _check_cancel(cancel_path)
                frame_started = time.perf_counter()
                read_started = time.perf_counter()
                raw = _read_frame(decode.stdout, frame_size)
                if not raw:
                    break
                if len(raw) != frame_size:
                    raise RuntimeError("Decoder returned a truncated frame")
                frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
                if hashes is not None:
                    hashes['decoded_rgb'].update(raw)
                decoded_pipe_bytes += len(raw)
                metrics.observe('decode_read', time.perf_counter() - read_started)
                with metrics.measure('temporal_guard'):
                    if offline_window is None:
                        cut = synthesizer.is_scene_cut(frame)
                    else:
                        cut = (
                            inferred_frame is not None
                            and is_offline_scene_cut(
                                inferred_frame,
                                frame,
                                policy.scene_cut_threshold,
                            )
                        )
                    refresh = depth_refresh_reason(frame, inferred_frame, decoded_frames, policy, cut)
                if cut:
                    backend.reset(engine, 'scene_cut')
                    scene_cut_resets += 1
                    if last_depth is not None and decoded_frames % policy.inference_cadence != 0:
                        extra_cut_inferences += 1
                if refresh in ('motion', 'local_motion'):
                    extra_motion_inferences += 1
                    local_motion_inferences += int(refresh == 'local_motion')
                if refresh != 'reuse':
                    with metrics.measure('preprocess'):
                        tensor = backend.prepare(frame)
                    with metrics.measure('depth_inference'):
                        last_depth = backend.infer(engine, tensor)
                    # Holds one immutable decoded RGB buffer, not a growing history.
                    inferred_frame = frame
                if offline_window is None:
                    ready = ((frame, last_depth),)
                else:
                    with metrics.measure('offline_depth_window'):
                        ready = offline_window.submit(frame, last_depth, cut_before=cut)
                for output_frame, output_depth in ready:
                    write_sample(output_frame, output_depth)
                decoded_frames += 1
                metrics.observe('frame_total', time.perf_counter() - frame_started)
            if offline_window is not None:
                with metrics.measure('offline_depth_window'):
                    remaining = offline_window.finish()
                for output_frame, output_depth in remaining:
                    write_sample(output_frame, output_depth)
            if interpolator is not None:
                for sample in interpolator.finish():write_stereo(sample)
            if frames!=decoded_frames*(2 if vfg else 1):
                raise RuntimeError('File processing changed the expected frame count')
            lifecycle.checkpoint('frame_loop')
            _check_cancel(cancel_path)
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
            projection_stats = projection.telemetry() if projection is not None else None
            vfg_stats=({**interpolator.telemetry(),'resources':vfg_session.telemetry()}
                       if interpolator is not None else {'enabled':False})
            lifecycle.checkpoint('resource_snapshot')
        lifecycle.checkpoint('backend_close')
        if frames == 0:
            raise RuntimeError("No video frames were decoded")
        _check_cancel(cancel_path)
        mux = _run([
            _tool("ffmpeg"), "-y", "-v", "error", "-i", str(video_path),
            "-i", str(input_path), "-map", "0:v:0", "-map", "1:a?",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
            "-movflags", "+faststart", str(partial_path),
        ])
        if mux.returncode != 0:
            raise RuntimeError("Audio mux failed: " + mux.stderr.strip())
        lifecycle.checkpoint('audio_mux')
        _check_cancel(cancel_path)
        if not partial_path.is_file() or partial_path.stat().st_size == 0:
            raise RuntimeError("Mux produced no final media")
        # Finish every fallible owned cleanup before replacing an existing result.
        # Otherwise a late pipe/temp cleanup error could report failure after publication.
        cleanup_errors = _cleanup_processes((decode, encode))
        decode = encode = None
        if cleanup_errors:
            raise ExceptionGroup('Pipeline cleanup failed', cleanup_errors)
        video_path.unlink(missing_ok=True)
        video_path = None
        _check_cancel(cancel_path)
        if cancel_path is not None:
            cancel_path.unlink(missing_ok=True)
            cancel_path = None
        partial_path.replace(output_path)
        partial_path = None
        lifecycle.checkpoint('publish')
        elapsed = time.perf_counter() - started
        result = {
            "event": "complete", "output": str(output_path), "frames": frames,
            "elapsed_seconds": elapsed, "processing_fps": frames / elapsed,
            "mode": mode, "policy": policy.__dict__,
            'output_fps':output_fps,'depth_strength':depth_strength,'vfg':vfg_stats,
            'decoded_frames':decoded_frames,'source_processing_fps':decoded_frames/elapsed,
            'output_codec': output_codec, 'output_policy': output_policy.__dict__,
            'stereo_layout': stereo_layout, 'output_width': packed_width, 'output_height': packed_height,
            'depth_backend': backend.describe(),
        }
        result['telemetry'] = {
            'diagnostic_hashes': {name: value.hexdigest() for name, value in hashes.items()} if hashes is not None else None,
            'schema_version': 2, 'sample_capacity': metrics.capacity,
            'percentile_scope': 'trailing_window', 'stages': metrics.summary(),
            'resources': resource_stats,
            'host_pipe_payload_bytes': {
                'decoded_rgb': decoded_pipe_bytes, 'encoded_sbs_rgb': encoded_pipe_bytes,
            },
            'scheduling_contract': {
                'worker_active_frame_limit': 1, 'application_work_queue_capacity': 0,
                'external_buffering_measured': False,
                'offline_depth_window_capacity': offline_window.capacity if offline_window is not None else 0,
            },
            'zero_copy': False,
            'scene_cut_resets': scene_cut_resets,
            'extra_cut_inferences': extra_cut_inferences,
            'extra_motion_inferences': extra_motion_inferences,
            'local_motion_inferences': local_motion_inferences,
            'offline_depth': offline_window.telemetry() if offline_window is not None else {'enabled': False},
            'stereo': {'algorithm': projection.algorithm if projection is not None else 'forward_zbuffer_cpu',
                       'projection_resources': projection_stats,
                       'flat_background_frames': synthesizer.flat_background_frames,
                       'letterbox': synthesizer.padding.telemetry() if synthesizer.padding is not None else {'enabled': False}},
            'lifecycle_seconds': dict(lifecycle.seconds),
            'probe_seconds': probe_seconds,
            'job_elapsed_seconds': time.perf_counter() - job_started,
        }
    except InterruptedError:
        progress({"event": "cancelled", "frames": frames})
        raise
    except BaseException:
        raise
    finally:
        primary = sys.exception()
        cleanup_errors = _cleanup_processes((decode, encode))
        for path in (partial_path, video_path, cancel_path):
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except Exception as error:
                    cleanup_errors.append(error)
        if cleanup_errors:
            cleanup = ExceptionGroup('Pipeline cleanup failed', cleanup_errors)
            if primary is not None:
                primary.add_note(repr(cleanup))
            else:
                raise cleanup
    progress(result)
    return result
