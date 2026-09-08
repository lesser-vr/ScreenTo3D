"""Public-launcher 720p/1080p/4K HEVC/cut compatibility matrix."""
import json
from pathlib import Path
import subprocess
import uuid
import cv2
from da2_base_experiment import ROOT


def main():
    root=ROOT/'out/da2-base-matrix'/uuid.uuid4().hex
    root.mkdir(parents=True)
    ffmpeg=ROOT/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg/ffmpeg.exe'
    ffprobe=ffmpeg.with_name('ffprobe.exe')
    original=ROOT/'out/vda-widescreen-fixtures/e27e0df90d9949e885fc6c3e12aecacb/avatar-1080p.mp4'
    report=dict(passed=False,runs=[])
    def command(args):
        subprocess.run([str(v) for v in args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        command([ffmpeg,'-v','error','-i',original,'-vf','scale=1280:720','-c:v','libx264','-c:a','aac',root/'720p.mp4'])
        command([ffmpeg,'-v','error','-f','lavfi','-i','color=white:s=1280x720:r=24:d=1',
            '-f','lavfi','-i','color=black:s=1280x720:r=24:d=1','-f','lavfi','-i','sine=frequency=440:duration=2',
            '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-map','2:a',
            '-c:v','libx265','-c:a','aac','-tag:v','hvc1',root/'cut.mp4'])
        fixtures=[('720p',root/'720p.mp4',1280,720,124,'h264'),
            ('1080p',original,1920,1080,124,'h264'),
            ('4k',ROOT/'out/vda-widescreen/07afaccdee26490c8262cc61b90b646f/input-4k-hevc.mp4',3840,2160,12,'hevc'),
            ('cut',root/'cut.mp4',1280,720,48,'hevc')]
        for name,path,w,h,count,codec in fixtures:
            output=root/f'{name}-sbs.mp4'
            result=subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/run-da2-base.ps1'),
                '-InputVideo',str(path),'-OutputVideo',str(output),'-OutputCodec',codec],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            (root/f'{name}.log').write_text(result.stdout+'\n'+result.stderr)
            if result.returncode:raise RuntimeError(result.stderr)
            events=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
            completed=next(e for e in events if e['event']=='complete')
            assert completed['frames']==count
            assert completed['telemetry']['resources']['input_shape']==[1,3,518,924]
            if name=='cut':assert completed['telemetry']['scene_cut_resets']==1
            streams=json.loads(subprocess.check_output([str(ffprobe),'-v','error','-show_streams','-of','json',str(output)]))['streams']
            assert any(s['codec_type']=='audio' for s in streams)
            video=next(s for s in streams if s['codec_type']=='video')
            assert video['codec_name']==codec
            capture=cv2.VideoCapture(str(output)); decoded=0
            try:
                while True:
                    ok,frame=capture.read()
                    if not ok:break
                    assert frame.shape==(h,w*2,3)
                    decoded+=1
            finally:capture.release()
            assert decoded==count
            report['runs'].append(dict(name=name,decoded=decoded,result=completed))
            print('PASS: '+name,flush=True)
        report['passed']=True
    finally:
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(root/'report.json',flush=True)


if __name__=='__main__':main()
