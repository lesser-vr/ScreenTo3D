"""Owned synthetic videos through real desktop QProcess workers and the default GPU model.

Never shuts down Windows: the shutdown command is replaced before any job starts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from unittest.mock import Mock

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from screento3d_app.desktop import DesktopController
from screento3d_app.desktop_preferences import DesktopPreferences


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--media-tools',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--vfg',action='store_true')
    parser.add_argument('--model',choices=['da2-small','da2-base','vda-small'],default='da2-base')
    parser.add_argument('--offline',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    app=QApplication.instance() or QApplication([])
    ffmpeg,ffprobe=(args.media_tools/(name+'.exe') for name in ('ffmpeg','ffprobe'))
    report=dict(passed=False,cases=[],vfg=args.vfg,model=args.model,scope='Real desktop workers, generated videos and Half TB; no visual-quality or processing-speed claim')
    def run(command):return subprocess.run(list(map(str,command)),capture_output=True,check=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
    def pump_until(predicate,timeout=120):
        end=time.monotonic()+timeout
        while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.01)
        assert predicate(),'Worker did not finish in the bounded test period'
    try:
        for scenario in ('success','cancel','failure'):
            folder=args.output/scenario;folder.mkdir()
            c=DesktopController(DesktopPreferences(QSettings(str(folder/'settings.ini'),QSettings.IniFormat)))
            forbidden=Mock(side_effect=AssertionError('Real Windows shutdown is forbidden'))
            c.shutdown.command=forbidden
            c.values['media']=str(args.media_tools.resolve())
            c.values['vfg']=args.vfg
            mode='offline-quality' if args.offline else {'da2-small':'performance','da2-base':'balanced','vda-small':'video-quality'}[args.model]
            if args.offline and args.model!='vda-small':raise ValueError('--offline requires --model vda-small')
            c.selectDepthModel(mode+'/'+args.model)
            states=[]
            def changed():
                state=[r['state'] for r in c.rows]
                if not states or states[-1]!=state:states.append(state)
                if 'running' in state:assert c.lease.owner=='file'
            c.changed.connect(changed)
            completed_events=[]
            original_event=c._event
            def record_event(event):
                if event.get('event')=='complete':completed_events.append(event)
                original_event(event)
            c._event=record_event
            sources=[]
            for i in range(2):
                source=folder/f'generated-{i}.mp4'
                if scenario=='failure' and i==0:
                    source.write_bytes(b'invalid test-only media')
                else:
                    run([ffmpeg,'-v','error','-nostdin','-f','lavfi','-i','testsrc2=size=320x180:rate=24',
                         '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','0.5',
                         '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-shortest',source])
                sources.append(source)
            hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in sources]
            c.add_paths([str(p) for p in sources])
            assert c.settings['model']==args.model and c.settings['stereo_layout']=='half-tb'
            if scenario=='failure':c.shutdown.setSelected(True)
            try:
                c.start()
                assert c.busy,c.status
                if scenario=='cancel':c.cancel()
                pump_until(lambda:not c.busy)
                expected=['completed','completed'] if scenario=='success' else [scenario=='cancel' and 'cancelled' or 'failed','queued']
                assert [r['state'] for r in c.rows]==expected,(c.status,states)
                assert not c.shutdown.pending and not c.shutdown.selected
                forbidden.assert_not_called()
                outputs=[]
                for row in c.rows:
                    output=Path(row['output']);assert '_Half_TB' in output.name
                    if scenario=='success':
                        metadata=json.loads(run([ffprobe,'-v','error','-count_frames','-show_streams','-of','json',output]).stdout)
                        video=next(s for s in metadata['streams'] if s['codec_type']=='video')
                        expected_frames=24 if args.vfg else 12
                        assert (video['width'],video['height'],int(video['nb_read_frames']))==(320,180,expected_frames)
                        from fractions import Fraction
                        assert Fraction(video['avg_frame_rate'])==(48 if args.vfg else 24)
                        source_meta=json.loads(run([ffprobe,'-v','error','-show_streams','-of','json',row['source']]).stdout)
                        original_video=next(s for s in source_meta['streams'] if s['codec_type']=='video')
                        self_duration=float(video['duration']);original_duration=float(original_video['duration'])
                        assert abs(self_duration-original_duration)<=1/48+.001
                        audio=next(s for s in metadata['streams'] if s['codec_type']=='audio')
                        original_audio=next(s for s in source_meta['streams'] if s['codec_type']=='audio')
                        assert abs(float(audio['duration'])-float(original_audio['duration']))<=1/24+.001
                        assert sum(s['codec_type']=='audio' for s in metadata['streams'])==1
                        run([ffmpeg,'-v','error','-xerror','-i',output,'-f','null','-'])
                        outputs.append(dict(name=output.name,frames=expected_frames,fps=48 if args.vfg else 24,size=[320,180],
                                            duration=self_duration,source_duration=original_duration,audio_duration=float(audio['duration']),
                                            audio=True,decoded=True))
                    else:assert not output.exists()
                assert hashes==[hashlib.sha256(p.read_bytes()).hexdigest() for p in sources]
                if scenario=='success':assert ['completed','running'] in states
                if scenario=='success' and args.vfg:
                    assert len(completed_events)==2
                    for event in completed_events:
                        assert event['vfg']['resources']['engine']=='nvidia-vfg'
                        assert event['vfg']['generated_frames']>0
                        assert event['vfg']['resources']['calls']==event['vfg']['generated_frames']
                        assert event['vfg']['tail_repeats']==1 and event['decoded_frames']==12
                        assert event['depth_strength']==.5
                report['cases'].append(dict(scenario=scenario,passed=True,states=states,outputs=outputs,
                    interpolation=[event.get('vfg',{}) for event in completed_events]))
            finally:
                if c.process is not None:
                    c.cancel();pump_until(lambda:c.process is None,30)
                c.shutdown.cancel();c.deleteLater();app.processEvents()
        report['passed']=True
    finally:(args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
