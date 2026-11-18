"""Owned synthetic host output, inspecting unchanged 8px/14px stereo overlays."""
import argparse,json,time
from pathlib import Path
from PySide6.QtCore import QObject,QSettings
from PySide6.QtGui import QImage,QColor
from screento3d_app.desktop import create_app
from screento3d_app.desktop_preferences import DesktopPreferences
from screento3d_app.capture_mailbox import WIDTH,HEIGHT
from screento3d_app.messages import Message as M
from screento3d_app.typography import FAMILY
import shiboken6


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    app,engine,c=create_app(DesktopPreferences(QSettings(str(args.output/'preferences.ini'),QSettings.IniFormat)))
    live=c.live;output=live.output_window;live.output_placement.path=args.output/'placement.json'
    report=dict(passed=False,scope='Synthetic image, forced visible performance overlay in an owned window; no inference, capture or actual stereo/device acceptance',cases=[])
    def pump():
        end=time.monotonic()+.2
        while time.monotonic()<end:app.processEvents();time.sleep(.003)
    def visual_items(item,name):
        result=[item] if item.objectName()==name else []
        for child in item.childItems():result.extend(visual_items(child,name))
        return result
    try:
        live.native_selected=False
        output.resize(1280,720);output.showNormal();pump()
        for layout,width,height in [('full-sbs',3840,1080),('half-sbs',1920,1080),('full-tb',1920,2160),('half-tb',1920,1080)]:
            live.setStereoLayout(layout)
            live.meta[WIDTH]=width;live.meta[HEIGHT]=height
            live.provider.image=QImage(width,height,QImage.Format_RGB32);live.provider.image.fill(QColor('#17191d'))
            live.version+=1;live.changed.emit();live.frameChanged.emit();pump()
            stats=c.main_window.findChild(QObject,'fullscreenStatsOverlay');stats.setProperty('visible',True)
            output.setProperty('stats','Source 60 · Output 60 · Interpolated 0 fps · Latency 16 ms · GPU 45%')
            live.notifyVfg(M('Preparing VFG…'),True);pump()
            stats_labels=visual_items(output.contentItem(),'stereoStatsLabel')
            notice_labels=visual_items(output.contentItem(),'vfgNoticeLabel')
            assert len(stats_labels)==len(notice_labels)==2
            for item in stats_labels:
                assert item.property('font').family()==FAMILY
                assert item.property('font').pixelSize()==8
                assert item.property('color').name()=='#00ff00'
            for item in notice_labels:
                assert item.property('font').family()==FAMILY
                assert item.property('font').pixelSize()==14
            assert output.grabWindow().save(str(args.output/(layout+'.png')))
            report['cases'].append(dict(layout=layout,stats_font_px=8,vfg_font_px=14,family=FAMILY))
        report['dpi']=output.devicePixelRatio();report['passed']=True
    finally:
        output.hide();c.main_window.close();app.processEvents();shiboken6.delete(engine)
        (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
if __name__=='__main__':main()
