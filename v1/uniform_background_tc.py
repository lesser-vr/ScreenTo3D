"""Uniform-background TC data/metrics, CPU-only and independent of private paths."""
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import cv2
import numpy as np
from depthsbs_app.stereo import uniform_color_mask

ROOT=Path(__file__).resolve().parents[1]
CASE_PATH=ROOT/'tests/media/uniform-background.json'


def load_case():
    return json.loads(CASE_PATH.read_text(encoding='utf-8'))


def fixture_path(case,root=ROOT):
    path=(root/case['path']).resolve()
    if not path.is_relative_to((root/'tests/media/local').resolve()):
        raise ValueError('Test media path escapes local fixture directory')
    return path


def verify_asset(case,root=ROOT):
    path=fixture_path(case,root)
    if not path.is_file():
        raise FileNotFoundError(f"Missing local {case['id']} excerpt: {case['path']}; restore the short fixture, not the original full video")
    if path.stat().st_size!=case['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=case['sha256']:
        raise ValueError('Uniform-background test media checksum/size mismatch')
    return path


def observe_pattern(rgb,case):
    border=np.concatenate((rgb[0],rgb[-1],rgb[:,0],rgb[:,-1]))
    color=np.median(border,axis=0).astype(np.float32)
    uniform=float(np.mean(np.max(np.abs(border.astype(np.float32)-color),axis=1)<=.04*255))
    coverage=float(uniform_color_mask(rgb,color,.04).mean())
    limits=case['pattern']
    return dict(uniform_border=uniform,matching_coverage=coverage,
                qualifies=uniform>=limits['minimum_uniform_border'] and
                limits['minimum_matching_coverage']<=coverage<=limits['maximum_matching_coverage'])


def inspect_clip(path,case):
    cap=cv2.VideoCapture(str(path));samples=[];count=0
    try:
        if not cap.isOpened():raise ValueError('Cannot decode uniform-background fixture')
        if abs(cap.get(cv2.CAP_PROP_FPS)-case['fps'])>.01:raise ValueError('Unexpected fixture frame rate')
        selected={0,case['frames']//3,2*case['frames']//3,case['frames']-1}
        for i in range(case['frames']+1):
            ok,bgr=cap.read()
            if not ok:break
            if bgr.shape!=(case['height'],case['width'],3):raise ValueError('Unexpected fixture geometry')
            count+=1
            if i in selected:samples.append(dict(frame=i,**observe_pattern(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB),case)))
        if count!=case['frames']:raise ValueError('Unexpected decoded fixture frame count')
        if not samples or sum(s['qualifies'] for s in samples)/len(samples)<case['pattern']['minimum_qualifying_samples']:
            raise ValueError('Fixture does not exercise uniform-background object case')
        return dict(decoded_frames=count,fps=case['fps'],size=[case['width'],case['height']],samples=samples)
    finally:cap.release()


def generated_frames(width=320,height=180,frames=24):
    """Repository-owned moving silhouette, thin lines and uniform dark backdrop."""
    for i in range(frames):
        rgb=np.zeros((height,width,3),np.uint8)
        cx=width//2+round(width*.03*np.sin(i*.3));cy=height//2
        cv2.ellipse(rgb,(cx,cy),(width//8,height//3),i*2,0,360,(210,70,25),-1)
        cv2.line(rgb,(cx,cy),(cx-width//6,cy+height//3),(60,190,30),1)
        cv2.line(rgb,(cx,cy),(cx+width//6,cy-height//3),(60,190,30),1)
        cv2.circle(rgb,(cx+width//24,cy-height//9),max(1,height//20),(240,180,40),-1)
        yield rgb


def generated_media(ffmpeg,path):
    case=load_case();case.update(width=320,height=180,frames=24,fps=60,duration_seconds=.4)
    payload=b''.join(frame.tobytes() for frame in generated_frames())
    subprocess.run([str(ffmpeg),'-v','error','-n','-f','rawvideo','-pix_fmt','rgb24','-s','320x180','-r','60',
                    '-i','pipe:0','-an','-c:v','libx264','-preset','ultrafast','-crf','18','-pix_fmt','yuv420p',str(path)],
                   input=payload,capture_output=True,check=True,timeout=30)
    return inspect_clip(path,case)


def assess_performance(report,case):
    limits=case['performance'];results=[]
    # Historical diagnostic reports used the old CPU-stage name.
    def background_ms(window):
        return window.get('background_ms',window.get('cpu_background_ms'))['median']
    for size in limits['sizes']:
        groups={mode:[w for row in report['rows'] if row['clip']=='flower' and row['size']==size and row['background'] is mode
                      for w in row['windows']] for mode in (None,False)}
        normal,control=groups[None],groups[False]
        result=dict(size=size,status='inconclusive',reasons=[])
        if min(len(normal),len(control))<limits['minimum_windows_per_condition']:
            result['reasons'].append('Insufficient normal/control windows')
        else:
            values=[w['fps'] for w in (*normal,*control)]+[background_ms(w) for w in normal]
            if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in values):
                result['reasons'].append('Invalid performance measurements')
                results.append(result)
                continue
            fps=statistics.median(w['fps'] for w in normal);reference=statistics.median(w['fps'] for w in control)
            background=statistics.median(background_ms(w) for w in normal)
            result.update(normal_fps=fps,control_fps=reference,ratio=fps/max(reference,1e-9),background_ms=background)
            if background>limits['maximum_background_stage_ms']:result['reasons'].append('Background stage exceeds frame budget')
            if result['ratio']<limits['minimum_normal_to_control_fps']:result['reasons'].append('Uniform-background output throughput collapse')
            result['status']='failed' if result['reasons'] else 'inconclusive' if reference<limits['minimum_control_fps'] else 'passed'
            if result['status']=='inconclusive':result['reasons'].append('Control/source throughput too low')
        results.append(result)
    return dict(case_id=case['id'],status='failed' if any(r['status']=='failed' for r in results) else
                'passed' if all(r['status']=='passed' for r in results) else 'inconclusive',results=results)
