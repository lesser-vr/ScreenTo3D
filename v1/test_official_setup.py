"""Real packaged first-use components, model setup and short GPU file outputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from unittest.mock import patch
import shiboken6

from PySide6.QtCore import QSettings
from depthsbs_app.desktop import create_app
from depthsbs_app.desktop_preferences import DesktopPreferences
from depthsbs_app import download_cache
from depthsbs_app.optional_models import installed_path,source_for,PACKS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--download-cache',required=True,type=Path)
    parser.add_argument('--public-models',action='store_true',help='Require public remote model origins and no bundled model archives')
    parser.add_argument('--installed-cache',type=Path,help='Reuse an explicitly selected QA LOCALAPPDATA instead of rebuilding unchanged engines')
    args=parser.parse_args();args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=False)
    # Every installed payload/engine and preference belongs to this QA run.
    os.environ['LOCALAPPDATA']=str(args.installed_cache.resolve() if args.installed_cache else args.output/'local')
    report=dict(passed=False,scope=__doc__,cases=[],download_cache='full-hash-verified artifacts; originals may be reused',public_models=args.public_models,installed_cache_reused=args.installed_cache is not None)
    preferences=DesktopPreferences(QSettings(str(args.output/'preferences.ini'),QSettings.IniFormat))
    preferences.store.setValue('ui/language','ko')
    with patch.object(download_cache,'cache_root',return_value=args.download_cache.resolve()):
        app,engine,c=create_app(preferences)
        c.shutdown.command=lambda:(_ for _ in ()).throw(AssertionError('No OS shutdown permitted'))
        errors=[];c.live.errorOccurred.connect(errors.append)
        installed=[];last=''
        def wait(predicate,timeout=1200):
            nonlocal last
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline and not predicate():
                app.processEvents();time.sleep(.01)
                assert not errors and not c.error_dialog.isVisible(),(errors,c.status,c.downloads.status)
                state=c.downloads.activeKey or c.status
                if state!=last:
                    last=state;print(state,flush=True)
            assert predicate(),(c.status,c.downloads.status,errors)
            assert not c.error_dialog.isVisible(),c.downloads.status
        def persist():
            (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        try:
            for key in ('da2-base','vda-small'):
                path=source_for(key)
                if args.public_models:
                    assert isinstance(path,str) and path.startswith('https://github.com/lesser-vr/ScreenTo3D-Models/releases/download/'),path
                else:
                    assert path.parent.name=='packs' and path.is_file()
                    with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==PACKS[key].sha
            # The explicit setup action uses original publisher sources with no sidecars.
            keys=['trt-core',c.gpuRuntimeKey,'media-tools']
            done=[]
            if c.downloads.ensure(keys,lambda:done.append(True)):done.append(True)
            wait(lambda:bool(done),120)
            assert not errors and not c.busy
            ffmpeg=installed_path('media-tools')/'ffmpeg.exe';ffprobe=ffmpeg.with_name('ffprobe.exe')
            source=args.output/'owned.mp4'
            subprocess.run([str(ffmpeg),'-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=24',
                            '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','0.5',
                            '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
            c.add_paths([str(source)])
            for mode,key in (('performance','da2-small'),('balanced','da2-base'),('video-quality','vda-small')):
                c.selectDepthModel(mode+'/'+key)
                target=args.output/(key+'-Half_TB.mp4');c.rows[0]['output']=str(target)
                c.rows[0]['state']='queued';c.rows[0]['auto_output']=False
                started=time.monotonic();c.start()
                wait(lambda:not c.busy and not c.downloads.setupVisible)
                assert c.rows[0]['state']=='completed' and target.is_file(),(key,c.status,c.downloads.status)
                data=json.loads(subprocess.check_output([str(ffprobe),'-v','error','-count_frames','-show_streams','-of','json',str(target)],timeout=30,creationflags=subprocess.CREATE_NO_WINDOW))
                video=next(stream for stream in data['streams'] if stream['codec_type']=='video')
                assert (video['width'],video['height'],int(video['nb_read_frames']))==(320,180,12)
                assert any(stream['codec_type']=='audio' for stream in data['streams'])
                subprocess.run([str(ffmpeg),'-v','error','-xerror','-i',str(target),'-f','null','-'],check=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
                report['cases'].append(dict(model=key,frames=12,geometry=[320,180],audio=True,decoded=True,setup_and_conversion_seconds=time.monotonic()-started))
                persist();print('PASS',key,flush=True)
            report['passed']=True
        finally:
            c.downloads.dismissSetup();c.shutdown.cancel()
            if c.busy:
                c.cancel()
                wait(lambda:not c.busy,90)
            c.main_window.close();persist();shiboken6.delete(engine)


if __name__=='__main__':main()
