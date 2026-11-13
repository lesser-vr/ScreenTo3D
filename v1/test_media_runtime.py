"""Opt-in real FFmpeg regressions for mux duration and corrupt-input cancellation."""
import argparse
import contextlib
import json
from pathlib import Path
import subprocess
import threading
import time
from unittest.mock import Mock,patch

import numpy as np
from screento3d_app import pipeline
from screento3d_app.media_process import MediaProcesses


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    ffmpeg=args.ffmpeg.resolve();ffprobe=ffmpeg.with_name('ffprobe.exe' if ffmpeg.suffix=='.exe' else 'ffprobe')
    report=dict(passed=False,scope='Real FFmpeg/NVENC and production pipeline; constant synthetic depth replaces inference only',mux=[],cancellation=None)
    def persist():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    def run(arguments):subprocess.run([str(ffmpeg),'-v','error',*arguments],check=True,timeout=30)
    def streams(path):
        return json.loads(subprocess.check_output([str(ffprobe),'-v','error','-count_frames','-show_streams','-of','json',str(path)],timeout=20))['streams']
    source=out/'video-short-audio.mp4'
    run(['-f','lavfi','-i','testsrc2=size=320x180:rate=24:duration=2','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=0.25','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)])
    long_audio=out/'long-audio.m4a';run(['-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=3','-c:a','aac',str(long_audio)])
    silent=out/'silent.mp4';run(['-i',str(source),'-map','0:v:0','-c:v','copy',str(silent)])
    try:
        with patch.object(pipeline,'_tool',side_effect=lambda name:str(ffmpeg if name=='ffmpeg' else ffprobe)):
            for name,audio,has_audio in [('short',source,True),('long',long_audio,True),('none',silent,False)]:
                target=out/(name+'-mux.mp4')
                with MediaProcesses() as media:
                    result=pipeline.mux_video(source,audio,target,has_audio,media=media)
                    assert result.returncode==0,result.stderr
                    pipeline.verify_output(target,48,320,180,24,media=media)
                video=next(s for s in streams(target) if s['codec_type']=='video')
                assert int(video['nb_read_frames'])==48,video
                report['mux'].append(dict(audio=name,frames=48,duration=float(video['duration'])));persist()
            engine=Mock();engine.infer.return_value=np.ones((1,518,518),np.float32);engine.telemetry.return_value={}
            complete=[];target=out/'pipeline-Half_TB.mp4'
            with patch.object(pipeline,'DepthEngine',return_value=contextlib.nullcontext(engine)):
                result=pipeline.convert_video(source,target,'performance',complete.append,stereo_layout='half-tb',depth_strength=.5)
            video=next(s for s in streams(target) if s['codec_type']=='video')
            assert int(video['nb_read_frames'])==result['frames']==48 and complete[-1]['event']=='complete'
            report['pipeline']=dict(frames=48,duration=float(video['duration']),audio=any(s['codec_type']=='audio' for s in streams(target)));persist()
            corrupt=out/'corrupt.mp4'
            run(['-f','lavfi','-i','testsrc2=size=160x90:rate=30:duration=20','-c:v','libx264','-tune','zerolatency','-bf','0',str(corrupt)])
            packets=json.loads(subprocess.check_output([str(ffprobe),'-v','error','-select_streams','v:0','-show_packets','-show_entries','packet=pos','-of','json',str(corrupt)],timeout=20))['packets']
            with corrupt.open('r+b') as file:
                for index,packet in enumerate(packets[1:],1):
                    file.seek(int(packet['pos']));file.write((0xffff0000+index).to_bytes(4,'big'))
            cancel=out/'cancel';target=out/'preserved.mp4';target.write_bytes(b'original result')
            ready=threading.Event();timer=threading.Timer(.3,cancel.touch)
            def progress(event):
                if event['event']=='start' and not ready.is_set():ready.set();timer.start()
            started=time.monotonic()
            try:
                with patch.object(pipeline,'DepthEngine',return_value=contextlib.nullcontext(engine)):
                    pipeline.convert_video(corrupt,target,'performance',progress,cancel,stereo_layout='half-tb')
            except (InterruptedError,RuntimeError) as error:failure=type(error).__name__
            else:raise AssertionError('Corrupt video must not be published as successful')
            finally:
                timer.cancel()
                if timer.ident is not None:timer.join(1)
            elapsed=time.monotonic()-started
            assert elapsed<5,elapsed
            assert target.read_bytes()==b'original result'
            assert not list(out.glob('.*.partial.mp4')) and not list(out.glob('.*.video-only.mp4'))
            report['corrupt_input']=dict(elapsed_seconds=elapsed,error=failure,cancel_requested=cancel.exists(),prior_result_preserved=True,temporary_files_removed=True)
            marker=out/'ffmpeg-cancel';timer=threading.Timer(.2,marker.touch);started=time.monotonic()
            with MediaProcesses(marker) as media:
                timer.start()
                try:
                    media.run([str(ffmpeg),'-v','error','-nostdin','-re','-f','lavfi',
                        '-i','testsrc2=size=160x90:rate=30:duration=10','-f','null','-'])
                except InterruptedError:pass
                else:raise AssertionError('FFmpeg wait must honor cancellation')
                finally:timer.cancel();timer.join(1)
            elapsed=time.monotonic()-started
            assert marker.exists() and elapsed<5
            assert all(child.closed and child.poll() is not None for child in media.children)
            report['cancellation']=dict(elapsed_seconds=elapsed,cancel_requested=True,children_reaped=True)
        report['passed']=True
    finally:persist()
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
