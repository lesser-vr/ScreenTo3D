"""Licensed public-video excerpts through all three accepted local backends."""
import json
from pathlib import Path
import subprocess
import sys
import uuid
import cv2
import numpy as np
from evaluate_depth_models import ROOT, sha, inspect_media
from screento3d_app import pipeline
from screento3d_app.resources import configure_media_tools
from vda_comparison import validate_runs, inspection_sheet


def main():
    source=ROOT/'out/public-video-source/bbb720/big_buck_bunny_720p_h264.mov'
    if sha(source) != '45c8bafeb9a53df7f491198d2e71529701bcf1cd51805782089fac1d32869f9b':
        raise ValueError('Public video does not match the recorded official source')
    root=ROOT/'out/public-video-tests'/uuid.uuid4().hex
    root.mkdir(parents=True)
    configure_media_tools(ROOT/'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal/ffmpeg')
    ffmpeg=ROOT/'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal/ffmpeg/ffmpeg.exe'
    attribution='(c) copyright 2008, Blender Foundation / www.bigbuckbunny.org; CC BY 3.0. Four-second excerpts transcoded to H.264/AAC and converted to SBS for local model comparison.'
    report=dict(passed=False,attribution=attribution,license_url='https://peach.blender.org/about/',
        source_url='https://download.blender.org/peach/bigbuckbunny_movies/big_buck_bunny_720p_h264.mov.zip',
        source_sha256=sha(source),archive_sha256=sha(source.parent.parent/'big_buck_bunny_720p_h264.mov.zip'),clips=[],
        scope='Three four-second public animation excerpts, qualitative diagnostics; no performance ranking or ground-truth depth score.')
    (root/'ATTRIBUTION.txt').write_text(attribution+'\n'+report['license_url']+'\n'+report['source_url'])
    print(root,flush=True)
    try:
        for name,start in [('bird-branches',20),('dark-fur-grass',40),('moving-foreground',180)]:
            folder=root/name;folder.mkdir()
            clip=folder/'input.mp4'
            subprocess.run([str(ffmpeg),'-v','error','-ss',str(start),'-i',str(source),'-t','4',
                '-map','0:v:0','-map','0:a:0','-c:v','libx264','-crf','18','-pix_fmt','yuv420p',
                '-c:a','aac',str(clip)],check=True)
            metadata=pipeline.probe_video(clip)
            assert (metadata['width'],metadata['height'],metadata['total_frames'])==(1280,720,96)
            record=dict(name=name,start_seconds=start,duration_seconds=4,input_sha256=sha(clip),metadata=metadata,runs={})
            report['clips'].append(record)
            for model in ('small','base','vda'):
                output=folder/f'{model}.mp4'
                with (folder/f'{model}.log').open('w') as log:
                    subprocess.run([sys.executable,str(ROOT/'v1/evaluate_depth_models.py'),'--input',str(clip),
                        '--one',model,'--output',str(output),'--hashes'],check=True,stdout=log,stderr=subprocess.STDOUT)
                record['runs'][model]=json.loads(output.with_suffix('.json').read_text())
                inspect_media(output,metadata)
                print('PASS: '+name+' / '+model,flush=True)
            validate_runs(record['runs'],96,96)
            captures=[cv2.VideoCapture(str(folder/f)) for f in ('input.mp4','small.mp4','base.mp4','vda.mp4')]
            try:
                for index in (0,48,95):
                    images=[]
                    for capture in captures:
                        capture.set(cv2.CAP_PROP_POS_FRAMES,index)
                        ok,image=capture.read();assert ok
                        images.append(image)
                    rows=[('SOURCE duplicated',np.concatenate([images[0],images[0]],axis=1)),
                          *[(model+' left / right',im) for model,im in zip(('Small','Base FP32','VDA'),images[1:])]]
                    assert cv2.imwrite(str(folder/f'eyes-{index}.jpg'),inspection_sheet(rows,1280,720))
            finally:
                for capture in captures:capture.release()
        assert sha(source)==report['source_sha256']
        report['passed']=True
    finally:
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(root/'report.json',flush=True)


if __name__=='__main__':main()
