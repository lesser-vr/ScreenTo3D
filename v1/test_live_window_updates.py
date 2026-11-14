"""No-capture Qt regression: frame updates should not repaint a control-only window."""
import argparse,json,time
from pathlib import Path
from PySide6.QtCore import QEventLoop,QSettings,QTimer,Qt
from screento3d_app.desktop import create_app
from screento3d_app.desktop_preferences import DesktopPreferences
import shiboken6

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    app,engine,c=create_app(DesktopPreferences(QSettings(str(args.output/'preferences.ini'),QSettings.IniFormat)))
    live=c.live;live.output_placement.path=args.output/'placement.json'
    main=c.main_window;output=live.output_window
    main.setPosition(30,35);output.setPosition(30,1010);output.resize(500,280);output.showNormal()
    counts=[0,0]
    def count(index):counts[index]+=1
    main.afterFrameEnd.connect(lambda:count(0));output.afterFrameEnd.connect(lambda:count(1))
    def pump(seconds):
        loop=QEventLoop();timer=QTimer();timer.setSingleShot(True);timer.setTimerType(Qt.PreciseTimer);timer.timeout.connect(loop.quit);timer.start(round(seconds*1000));loop.exec()
    report=dict(passed=False,scope='Synthetic frame notifications, real Qt/D3D11 windows; no capture or inference; not game FPS or final Owl3D output',cases=[])
    timer=QTimer();timer.setTimerType(Qt.PreciseTimer);timer.setInterval(16);ticks=[0]
    def frame():ticks[0]+=1;live.frameChanged.emit()
    timer.timeout.connect(frame)
    try:
        pump(.8)
        for visible in (False,True,False):
            live.setPreviewVisible(visible);pump(.3)
            before=list(counts);tick_before=ticks[0];timer.start();pump(1.2);timer.stop()
            row=dict(preview_visible=visible,notifications=ticks[0]-tick_before,control_renders=counts[0]-before[0],output_renders=counts[1]-before[1]);report['cases'].append(row)
            print(json.dumps(row),flush=True)
        assert all(row['output_renders']>=35 for row in report['cases']),report
        assert all(row['control_renders']<=5 for row in report['cases'] if not row['preview_visible']),report
        assert report['cases'][1]['control_renders']>=35,report
        report['passed']=True
    finally:
        timer.stop();main.close();output.hide();app.processEvents();shiboken6.delete(engine)
        (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
if __name__=='__main__':main()
