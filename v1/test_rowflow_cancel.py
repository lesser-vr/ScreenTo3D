"""Cancel actual app preparation, then restart through the default host output."""
import json
import os
from pathlib import Path
import time

import shiboken6
from benchmark_live_modes import ClockOracle
from screento3d_app.desktop import create_app


def main():
    output=Path('out/rowflow-cancel-host-20261105')
    output.mkdir(exist_ok=False)
    app,engine,desktop=create_app()
    oracle=ClockOracle('OfficeWalk');oracle.resize(758,426);oracle.show()
    live=desktop.live
    live.output_placement.path=output/'placement.json'
    errors=[];live.errorOccurred.connect(errors.append)

    def pump():
        app.processEvents();time.sleep(.005)

    def wait(predicate,seconds=120):
        end=time.monotonic()+seconds
        while not predicate() and time.monotonic()<end:pump()
        assert predicate(),live.status

    try:
        for _ in range(60):pump()
        live.items=[dict(kind='window',id=int(oracle.winId()),pid=os.getpid(),label=oracle.windowTitle(),
            width=round(oracle.width()*oracle.devicePixelRatioF()),height=round(oracle.height()*oracle.devicePixelRatioF()))]
        live.selected=0;live.setSbs(True);live.setMode('balanced');live.setProcessingPath('gpu')
        live.startSbs(0,0)
        wait(lambda:live.preparation is not None and bool(live.preparation.value))
        # Let poll deliver the preparation status before cancellation.
        wait(lambda:'최적화' in live.status)
        assert not live.hasFrame
        live.stop();wait(lambda:not live.active,15)
        assert desktop.lease.owner is None and not live.hasFrame and not errors,errors
        cancel_status=live.status
        live.startSbs(0,0)
        wait(lambda:live.hasFrame)
        assert live.stereo_renderer=='rowflow-sym' and not live.nativeEnabled
        wait(lambda:live._stats()[0]>=5)
        assert live.output_window.grabWindow().save(str(output/'host-output.png'))
        report=live.report()
        live.stop();wait(lambda:not live.active,15)
        assert desktop.lease.owner is None and not errors,errors
        report.update(passed=True,preparation_cancel=True,cancel_status=cancel_status,host_restart=True)
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(dict(passed=True,preparation_cancel=True,host_restart=True)),flush=True)
    finally:
        live.stop()
        wait(lambda:not live.active,15)
        oracle.close()
        if oracle.video is not None:oracle.video.release()
        shiboken6.delete(engine)


if __name__=='__main__':main()
