"""Actual WGC/Base/native Qt comparison, with observed original/generated IDs."""
import argparse
from collections import deque
import json
import os
from pathlib import Path
import time
import traceback

import numpy as np
import shiboken6
from PySide6.QtCore import Qt
from screento3d_app.desktop import create_app
from screento3d_app.live_sbs import DEFAULT_STEREO_QUALITY
from live_benchmark_source import SourceProcess
from benchmark_live_modes import memory_bytes
from native_path import install


from screento3d_app.environment import get as app_env

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", default="3840x2160", choices=("1920x1080", "3840x2160"))
    parser.add_argument("--vfg", action="store_true")
    parser.add_argument('--model',choices=('da2-base','da2-small'),default='da2-base')
    parser.add_argument("--strength", type=float, default=1.)
    parser.add_argument("--warmup", type=float, default=4)
    parser.add_argument("--seconds", type=float, default=4)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--lifecycle", action="store_true")
    parser.add_argument("--test-cut-every", type=int, default=0)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ["SCREENTO3D_VFG_EVIDENCE"] = str(args.output)
    os.environ["SCREENTO3D_VFG_TEST_CUT_EVERY"] = str(args.test_cut_every)
    install(args.vfg)
    app, engine, desktop = create_app()
    live = desktop.live
    live.output_window.setTransientParent(None)
    live.output_window.setFlag(Qt.WindowStaysOnTopHint, True)
    live.output_placement.path = args.output / "placement.json"
    source = SourceProcess("FloorballGame", interval_ms=0)
    samples = deque(maxlen=30000)
    last_seen = [0]
    report = dict(completed=False, vfg=args.vfg, model=args.model, size=args.size, strength=args.strength,
                  stereo_quality=app_env('SCREENTO3D_STEREO_QUALITY',DEFAULT_STEREO_QUALITY),
                  depth_history=app_env('SCREENTO3D_DEPTH_HISTORY','continuous'), rows=[], lifecycle={},
                  scope="Actual WGC + selected DA2 FP16 + CUDA SBS + optional Medium VFG + native Qt afterFrameEnd; not physical display latency")

    def save():
        (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    def on_frame():
        if live.native is None:
            return
        native = live.native.report()["output"]
        sequence = native["last_submitted_id"]
        if not sequence or sequence == last_seen[0]:
            return
        last_seen[0] = sequence
        record = live.native.records.get(sequence)
        if record is not None:
            samples.append((time.perf_counter_ns(), *record))

    connected = False

    def pump(seconds):
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            app.processEvents()
            time.sleep(.0005)

    def wait(predicate, timeout=90):
        until = time.monotonic()+timeout
        while not predicate():
            pump(.01)
            if time.monotonic()>until:
                raise TimeoutError(live.status)
            if not live.active and live.started:
                raise RuntimeError(live.status)

    def start():
        last_seen[0] = 0
        live.start()
        if not live.active:
            raise RuntimeError(live.status)
        live.showOutput(0,False)
        live.output_window.resize(1400,650)
        live.output_window.setPosition(0,50)
        wait(lambda: live.native.report()["output"]["submitted_frames"]>=5)

    def stop():
        live.stop()
        end=time.monotonic()+20
        while live.active and time.monotonic()<end:
            pump(.01)
        if live.active:
            raise RuntimeError("Owned worker did not stop")
        pump(.1)
        native=live.native.report()
        if native["live_pools"] or native["live_nodes"] or live.hasFrame:
            raise RuntimeError("Stale native output after stop")
        return native

    try:
        pump(.3)
        width,height=map(int,args.size.split("x"))
        source.resize(round(width/source.devicePixelRatioF()),round(height/source.devicePixelRatioF()))
        source.request("activate")
        pump(.3)
        live.items=[dict(kind="window",id=int(source.winId()),pid=source.pid,label="Public VFG benchmark",
                         width=width,height=height)]
        live.selected=0
        live.setSbs(True)
        live.setMode("performance" if args.model=='da2-small' else "balanced")
        live.setStrength(args.strength)
        live.setProcessingPath("gpu-texture")
        live.setPresentationHz(0)
        live.native.visible=lambda: live.output_window.isVisible()
        def notify_native_frame():
            live.version += 1
            live.notifyFrame()
        live.native.on_published = notify_native_frame
        start()
        # Connect after the native node's metrics callback, so IDs belong to this frame.
        live.output_window.afterFrameEnd.connect(on_frame, Qt.DirectConnection)
        connected = True
        desktop.main_window.hide()
        pump(args.warmup)
        for repeat in range(args.repeats):
            begin=time.perf_counter_ns()
            before=live.native.report()["output"]["submitted_frames"]
            base_before=live._stats()[0]
            source_before=source.request("snapshot")
            pump(args.seconds)
            if not live.active:
                raise RuntimeError(live.status)
            end=time.perf_counter_ns()
            after=live.native.report()["output"]["submitted_frames"]
            source_after=source.request("snapshot")
            current=[s for s in samples if begin<=s[0]<=end]
            duration=(end-begin)/1e9
            def latency(kind,index):
                values=[(s[0]-s[index])/1e6 for s in current if s[5]==kind]
                return dict(p50=float(np.median(values)),p95=float(np.percentile(values,95))) if values else None
            generated=sum(s[5]==1 for s in current)
            original=sum(s[5]==0 for s in current)
            # sample=(present,seq,due,source,oldest,kind,base_id,ready,callback)
            intervals=np.diff([s[0] for s in current])/1e6
            row=dict(repeat=repeat,seconds=duration,native_fps=(after-before)/duration,
                     base_fps=(live._stats()[0]-base_before)/duration,
                     observed_generated_fps=generated/duration,observed_original_fps=original/duration,
                     observed_count=len(current),native_count=after-before,
                     source_fps=(source_after['paint_count']-source_before['paint_count'])/duration,
                     original_source_age_ms=latency(0,3),generated_midpoint_age_ms=latency(1,3),
                     generated_oldest_input_age_ms=latency(1,4),
                     interval_ms=dict(p50=float(np.median(intervals)),p95=float(np.percentile(intervals,95))) if len(intervals) else None,
                     worker_private_bytes=memory_bytes(live.process.pid),last_processing_stats=live._stats())
            report["rows"].append(row)
            print(json.dumps(row),flush=True)
            save()
        if args.vfg and not any(row["observed_generated_fps"]>0 for row in report["rows"]):
            raise RuntimeError("VFG requested but no generated frames were presented")
        if args.lifecycle:
            live.output_window.hide();pump(.5)
            live.showOutput(0,False)
            old=live.native.report()["output"]["submitted_frames"]
            wait(lambda:live.native.report()["output"]["submitted_frames"]>old+5)
            report["lifecycle"]["hide_restore"]=True
            source.resize(round(1280/source.devicePixelRatioF()),round(720/source.devicePixelRatioF()))
            wait(lambda: live.native.pool is not None and live.native.pool.width==2560)
            old=live.native.report()["output"]["submitted_frames"]
            wait(lambda:live.native.report()["output"]["submitted_frames"]>old+5)
            report["lifecycle"]["resize"]=True
        report["stop_native"]=stop()
        report["lifecycle"]["stop_clear"]=True
        if args.lifecycle:
            start();pump(.5);stop()
            report["lifecycle"]["restart"]=True
            live.start();live.stop()
            end=time.monotonic()+20
            while live.active and time.monotonic()<end:pump(.01)
            assert not live.active and not live.hasFrame
            report["lifecycle"]["preparation_cancel"]=True
        report["samples"]=[list(s) for s in samples]
        if args.test_cut_every:
            cuts=[s for s in samples if s[6] % args.test_cut_every == 0]
            assert cuts and all(s[5]==0 for s in cuts), "Generated frame crossed a forced cut"
            report["lifecycle"]["forced_cut_original_only"]=True
        report["completed"]=True
        save()
    except BaseException:
        report["failure"]=traceback.format_exc()
        report["status"]=live.status
        report["native"]=live.native.report() if live.native else None
        report["observed_samples"]=list(samples)[-20:]
        save()
        raise
    finally:
        if live.active:
            try:stop()
            except Exception:pass
        source.close()
        if connected:
            live.output_window.afterFrameEnd.disconnect(on_frame)
        shiboken6.delete(engine)


if __name__=="__main__":
    main()
