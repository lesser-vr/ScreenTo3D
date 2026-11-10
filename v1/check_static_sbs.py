"""Exercise finished-SBS reuse on a private-to-the-test WGC window."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import time
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QTimer, Qt
import shiboken6

from depthsbs_app import live_sbs
from depthsbs_app.capture_mailbox import RECEIVED
from depthsbs_app.desktop import create_app
from live_benchmark_source import SourceProcess


def baseline_worker(*args, **kwargs):
    with patch('depthsbs_app.live_policy.StaticSbsReuse', return_value=None):
        return live_sbs.sbs_worker(*args, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    app, qml, desktop = create_app()
    live = desktop.live
    errors = []
    live.errorOccurred.connect(errors.append)
    live.output_placement.path = args.output/'placement.json'
    live.setPresentationHz(60)
    live.setProcessingPath('gpu-texture')
    live.setCursor(False)

    def pump(ms):
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.setTimerType(Qt.PreciseTimer)
        timer.timeout.connect(loop.quit)
        timer.start(ms)
        loop.exec()
        if errors:
            raise RuntimeError(errors[-1])

    def wait(test, seconds):
        end = time.monotonic()+seconds
        while not test():
            if time.monotonic()>end:
                raise TimeoutError(f'{live.status} stats={live._stats()}')
            pump(5)

    def counts():
        stats = live._stats()
        with live.mailbox.lock:
            received = live.mailbox.meta[RECEIVED]
        return dict(received=received, rendered=stats[0], inferred=stats[10],
                    held=stats[live_sbs.SBS_REUSED], submitted=live.native.report()['output']['submitted_frames'])

    def interval(seconds):
        start = counts()
        # Stream device telemetry while the Qt consumer runs normally.
        proc = subprocess.Popen(['nvidia-smi','--id=0','--query-gpu=utilization.gpu,power.draw',
                                 '--format=csv,noheader,nounits','-lms','200'],
                                stdout=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            pump(seconds*1000)
            end = counts()
        finally:
            proc.terminate()
            data = proc.communicate(timeout=5)[0]
        samples = [list(map(float,line.split(','))) for line in data.splitlines() if ',' in line]
        return dict(seconds=seconds, **{key:end[key]-start[key] for key in start},
                    gpu_percent=statistics.mean(row[0] for row in samples),
                    watts=statistics.mean(row[1] for row in samples))

    source = SourceProcess('FloorballGame',interval_ms=16)
    try:
        source.resize(round(3840/source.devicePixelRatioF()),round(2160/source.devicePixelRatioF()))
        source.request('activate')
        pump(200)
        source.request('repeat')
        live.items=[dict(kind='window',id=source.winId(),pid=source.pid,label='Owned static fixture',width=3840,height=2160)]
        live.select(0)
        for mode in ('balanced','performance'):
            live.setMode(mode)
            for enabled in (False,True):
                source.request('restore_repeat')
                worker = live_sbs.sbs_worker if enabled else baseline_worker
                with patch.object(live_sbs,'sbs_worker',worker):
                    live.startMinimal()
                wait(lambda:live.native and live.native.report()['output']['submitted_frames']>=4,90)
                shape=[live.native.pool.width,live.native.pool.height]
                assert shape==[7680,2160],shape
                if enabled:
                    wait(lambda:counts()['held']>=12,20)
                pump(1000)
                repeat = interval(5)
                if enabled:
                    assert repeat['held']>100 and repeat['rendered']<15, repeat
                    # Immediately after a real periodic check there is a full
                    # second before another check can publish the unchanged input.
                    last=counts()['submitted']
                    wait(lambda:counts()['submitted']>last,2)
                    pump(35)
                before = counts()['submitted']
                begin = time.perf_counter_ns()
                source.request('change_pixel')
                def fresh_submission():
                    output=live.native.report()['output']
                    return output['submitted_frames']>before and any(
                        f.sequence==output['last_submitted_id'] and f.source_ns>=begin
                        for f in live.native.frames.values())
                wait(fresh_submission,1)
                first_ms=(time.perf_counter_ns()-begin)/1e6
                source.request('pause')
                pump(500)
                idle = interval(2)
                if not idle['received']:
                    assert idle['rendered']==idle['held']==idle['submitted']==0, idle
                source.request('resume')
                before=counts()['submitted']
                wait(lambda:counts()['submitted']>=before+6,3)
                moving=interval(2)
                assert moving['held']==0 and moving['submitted']>0, moving
                source.request('repeat')
                settled_after_motion_ms=None
                if enabled:
                    started=time.perf_counter()
                    prior=counts()['held']
                    while counts()['held']==prior and time.perf_counter()-started<12:
                        pump(20)
                    if counts()['held']>prior:
                        settled_after_motion_ms=(time.perf_counter()-started)*1000
                live.stop()
                wait(lambda:not live.active,20)
                cleanup=live.native.report()
                assert cleanup['live_pools']==cleanup['live_nodes']==0
                report=dict(mode=mode,enabled=enabled,shape=shape,repeat=repeat,idle=idle,moving=moving,
                            settled_after_motion_ms=settled_after_motion_ms,
                            pixel_command_to_submission_ms=first_ms,cleanup=cleanup)
                (args.output/f'{mode}-{enabled}.json').write_text(json.dumps(report,indent=2))
                print(json.dumps(report),flush=True)
    finally:
        if live.active:
            live.stop()
            wait(lambda:not live.active,20)
        source.close()
        shiboken6.delete(qml)


if __name__=='__main__':
    main()
