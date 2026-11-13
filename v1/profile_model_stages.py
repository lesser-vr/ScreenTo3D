"""Bounded actual-backend P0 attribution, without changing product behavior.

Use the prepared VDA Python environment. oVDA requires explicit --noncommercial.
Decoded public frames are held in a bounded list; no desktop capture or SBS/VR
output is performed. Report success is published only after engine cleanup.
"""

import argparse
from contextlib import nullcontext
import hashlib
import inspect
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time

from depth_stage_probe import SourceRegions, model_plans

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stats(values):
    ordered = sorted(values)
    if not ordered:
        return None
    return {"count": len(ordered), "median": statistics.median(ordered),
            "min": ordered[0], "max": ordered[-1],
            "p95": ordered[min(len(ordered) - 1, int((len(ordered) - 1) * .95))]}


def command(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def load_frames(source, width, height, count):
    import cv2
    from public_test_media import CORPUS, SOURCES

    if source not in SOURCES:
        raise ValueError("Only pinned public fixtures are accepted")
    path = CORPUS / f"{source}.mp4"
    manifest = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    if digest(path) != manifest["sha256"]:
        raise ValueError("Public media checksum mismatch")
    capture = cv2.VideoCapture(str(path))
    frames = []
    try:
        for _ in range(count):
            ok, bgr = capture.read()
            if not ok:
                raise ValueError("Public fixture is too short")
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            frames.append(cv2.resize(rgb, (width, height), interpolation=cv2.INTER_LANCZOS4))
    finally:
        capture.release()
    return frames, manifest


class TrtEvents:
    def __init__(self, stream):
        import torch

        self.stream = stream
        self.start = torch.cuda.Event(enable_timing=True)
        self.end = torch.cuda.Event(enable_timing=True)
        self.start.record(stream)
        self.end.record(stream)
        stream.synchronize()
        self.started = self.ended = False

    def transition(self, old, new):
        if new == "trt_enqueue":
            if self.started:
                raise RuntimeError("Multiple TRT submissions in one depth call")
            self.start.record(self.stream)
            self.started = True
        if old == "trt_enqueue":
            self.end.record(self.stream)
            self.ended = True

    def milliseconds(self):
        if not self.started or not self.ended:
            raise RuntimeError("TRT region was not observed")
        return float(self.start.elapsed_time(self.end))


def one_frame(engine, frame, plans, traced, events=None):
    if traced:
        if events is None:
            raise ValueError("Preallocated events required")
        events.started = events.ended = False
    trace = SourceRegions(plans, events.transition) if traced else None
    before_cache = len(engine.history) if hasattr(engine, "history") else engine.used
    started = time.perf_counter_ns()
    with trace if traced else nullcontext():
        token = engine.infer_device(frame)
        engine.complete_device(token)
    wall = (time.perf_counter_ns() - started) / 1e6
    return {"wall_ms": wall, "history_before": before_cache,
            "host_regions_ms": {k: v / 1e6 for k, v in trace.elapsed.items()} if trace else None,
            "trt_stream_ms": events.milliseconds() if events else None}


def parity(engine, frames, plans):
    results = []
    for traced in (False, True):
        engine.reset("start")
        events = TrtEvents(engine.stream) if traced else None
        hashes = []
        for frame in frames[:3]:
            if events is not None:
                events.started = events.ended = False
            trace = SourceRegions(plans, events.transition) if traced else nullcontext()
            with trace:
                token = engine.infer_device(frame)
                try:
                    engine.stream.synchronize()
                    hashes.append(hashlib.sha256(token.tensor.cpu().numpy().tobytes()).hexdigest())
                finally:
                    engine.complete_device(token)
        results.append(hashes)
    if results[0] != results[1]:
        raise RuntimeError("Diagnostic tracing changed device-depth results")
    return {"exact": True, "frames": len(results[0]), "sha256": results[0],
            "scope": "Separate diagnostic D2H outside performance windows"}


def run_model(model, args, report):
    import torch

    if model == "vda":
        from screento3d_app.vda_device import VdaDeviceEngine

        engine = VdaDeviceEngine(ROOT / "out/vda-local/518x924-fp32", args.runtime)
    else:
        from screento3d_app.ovda import runtime_class

        engine = runtime_class(device_depth=True)(
            directory=ROOT / "out/ovda-local/518x924-fp32", runtime_dir=args.runtime,
            profile=(518, 924))
    try:
        plans = model_plans(model, engine)
        report["source_hashes"].update({inspect.getfile(code): digest(inspect.getfile(code))
                                        for code, _ in plans})
        report["environment"].update(torch=torch.__version__,
            torch_cpu_threads=torch.get_num_threads(), gpu=torch.cuda.get_device_name(),
            tensorrt=engine.trt.__version__)
        for size in args.sizes:
            width, height = map(int, size.split("x"))
            frames, manifest = load_frames(args.source, width, height, args.frames + args.warmup)
            report["media"] = manifest
            parity_result = parity(engine, frames, plans)
            for history in args.history:
                batches = []
                for repeat in range(args.repeats):
                    for traced in ((False, True) if repeat % 2 == 0 else (True, False)):
                        engine.reset("start")
                        for frame in frames[:args.warmup]:
                            if history == "reset-each-frame":
                                engine.reset("discontinuity")
                            token = engine.infer_device(frame)
                            engine.complete_device(token)
                        rows = []
                        events = TrtEvents(engine.stream) if traced else None
                        for index, frame in enumerate(frames[args.warmup:]):
                            reset_ms = 0.0
                            if history == "reset-each-frame":
                                started = time.perf_counter_ns()
                                engine.reset("discontinuity")
                                reset_ms = (time.perf_counter_ns() - started) / 1e6
                            row = one_frame(engine, frame, plans, traced, events)
                            row.update(frame=index, reset_ms=reset_ms)
                            rows.append(row)
                        batch = {"repeat": repeat, "traced": traced, "frames": rows,
                                 "mean_wall_ms": statistics.mean(row["wall_ms"] for row in rows)}
                        batches.append(batch)
                        print(f"{model} {size} {history} repeat={repeat} traced={traced} "
                              f"{batch['mean_wall_ms']:.3f}ms", flush=True)
                normal = [batch["mean_wall_ms"] for batch in batches if not batch["traced"]]
                measured = [batch["mean_wall_ms"] for batch in batches if batch["traced"]]
                overhead = (statistics.median(measured) / statistics.median(normal) - 1) * 100
                traced_rows = [row for batch in batches if batch["traced"] for row in batch["frames"]]
                labels = sorted({key for row in traced_rows for key in row["host_regions_ms"]})
                report["cases"].append({"model": model, "source_size": [width, height],
                    "model_input_hw": [518, 924], "history": history, "parity": parity_result,
                    "normal_batch_mean_ms": stats(normal), "traced_batch_mean_ms": stats(measured),
                    "instrumentation_overhead_percent": overhead,
                    "instrumentation_gate_passed": overhead <= args.max_overhead_percent,
                    "trt_stream_ms": stats([row["trt_stream_ms"] for row in traced_rows]),
                    "host_regions_ms": {key: stats([row["host_regions_ms"].get(key, 0)
                                                    for row in traced_rows]) for key in labels},
                    "batches": batches})
                checkpoint = args.output / "partial.json"
                checkpoint.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["model_telemetry"][model] = engine.telemetry()
    finally:
        engine.close()
    report["cleaned_models"].append(model)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", nargs="+", choices=("vda", "ovda"), default=["vda"])
    parser.add_argument("--sizes", nargs="+", choices=("1920x1080", "3840x2160"),
                        default=["1920x1080", "3840x2160"])
    parser.add_argument("--history", nargs="+", choices=("continuous", "reset-each-frame"),
                        default=["continuous", "reset-each-frame"])
    parser.add_argument("--source", choices=("FloorballGame", "OfficeWalk", "ParkingGarage"),
                        default="FloorballGame")
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=16)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--max-overhead-percent", type=float, default=10.0)
    parser.add_argument("--runtime", type=Path, default=Path("C:/TensorRT/TensorRT-11.2.1.2/bin"))
    parser.add_argument("--noncommercial", action="store_true")
    args = parser.parse_args()
    if (args.output.exists() or not 1 <= args.frames <= 32 or not 1 <= args.repeats <= 10
            or not 16 <= args.warmup <= 32 or not 0 <= args.max_overhead_percent <= 25):
        raise ValueError("Fresh output and bounded frame/repeat/overhead values required")
    if "ovda" in args.models and not args.noncommercial:
        raise ValueError("oVDA requires explicit personal/noncommercial confirmation")
    gpu = command("nvidia-smi", "--query-gpu=name,driver_version,utilization.gpu,memory.used",
                  "--format=csv,noheader")
    args.output.mkdir(parents=True)
    report = {"schema": "screento3d.model-stage-probe.v1", "status": "incomplete",
        "scope": "Isolated depth only; no capture, SBS, FG, display, VR or sustained throughput claim. "
                 "Host regions are exclusive wall times. TRT CUDA interval can contain host enqueue gaps. "
                 "Do not add CUDA intervals to host regions or add region percentiles together. "
                 "4K is upscaled prepared public 1080p footage. Reset-each-frame is a diagnostic, "
                 "not a changed product sampling policy. Reset time is separate from depth wall time.",
        "environment": {"commit": command("git", "rev-parse", "HEAD"),
                        "dirty": bool(command("git", "status", "--porcelain")),
                        "python": platform.python_version(), "os": platform.platform(),
                        "gpu_preflight": gpu},
        "configuration": {**vars(args), "output": str(args.output), "runtime": str(args.runtime)},
        "source_hashes": {str(Path(__file__).resolve()): digest(__file__),
                          str(ROOT / "v1/depth_stage_probe.py"): digest(ROOT / "v1/depth_stage_probe.py")},
        "cases": [], "model_telemetry": {}, "cleaned_models": []}
    with os.add_dll_directory(str(args.runtime.resolve(strict=True))):
        for model in args.models:
            run_model(model, args, report)
    report["status"] = "measured"
    report["all_instrumentation_gates_passed"] = all(case["instrumentation_gate_passed"]
                                                   for case in report["cases"])
    report["environment"]["gpu_after"] = command("nvidia-smi",
        "--query-gpu=name,driver_version,utilization.gpu,memory.used", "--format=csv,noheader")
    report_path = args.output / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(report_path, flush=True)


if __name__ == "__main__":
    main()
