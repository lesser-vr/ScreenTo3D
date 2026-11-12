"""Opt-in Windows Qt work-area regression using process-local DPI only."""
import argparse,json,os,time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scale',type=float,default=1)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    os.environ['LOCALAPPDATA']=str(out/'local');os.environ['QT_SCALE_FACTOR']=str(args.scale)
    from PySide6.QtCore import QSettings,QPointF,QRect
    from PySide6.QtQuick import QQuickItem,QQuickWindow
    import shiboken6
    from depthsbs_app.desktop import create_app
    from depthsbs_app.desktop_preferences import DesktopPreferences
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'settings'))
    app,engine,c=create_app(DesktopPreferences(QSettings(str(out/'prefs.ini'),QSettings.IniFormat)))
    warnings=[];engine.warnings.connect(lambda errors:warnings.extend(e.toString() for e in errors))
    report=dict(passed=False,scope='Actual Qt controls and minimum sizes; process-local DPI; isolated preferences',rows=[])
    def pump():
        end=time.monotonic()+.15
        while time.monotonic()<end:app.processEvents();time.sleep(.003)
    try:
        window=c.main_window;pump();area=window.screen().availableGeometry()
        report.update(device_pixel_ratio=window.screen().devicePixelRatio(),available=[area.width(),area.height()])
        for page in (1,0,1,3,1):
            window.setProperty('page',page);pump()
            target=window.findChild(QQuickWindow,'toolsWindow') if page==3 else window
            outer=target.frameGeometry()
            assert area.contains(outer),(page,area,outer)
            row=dict(page=page,width=target.width(),height=target.height(),frame_fits=True)
            if page==1:
                button=window.findChild(QQuickItem,'convertButton')
                point=button.mapToScene(QPointF(0,button.height()))
                bottom=window.y()+point.y()
                assert bottom<=area.bottom()+1,(bottom,area.bottom())
                row['convert_button_bottom']=bottom
                assert window.grabWindow().save(str(out/f'files-{len(report["rows"])}.png'))
            report['rows'].append(row)
        assert not warnings,warnings
        report['passed']=True
    finally:
        c.main_window.close();shiboken6.delete(engine)
        report['warnings']=warnings;(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
