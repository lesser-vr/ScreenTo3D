"""Postdecode timing/audio checks for the recorded expansion matrix."""
from fractions import Fraction
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
MEDIA=ROOT/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg'
FOLDER=ROOT/'out/ovda-expanded-gate/05d776718fdf4cbcbe4af9f423c3f598'


def probe(path):
    streams=json.loads(subprocess.check_output([str(MEDIA/'ffprobe.exe'),'-v','error','-show_streams','-of','json',str(path)]))['streams']
    frames=json.loads(subprocess.check_output([str(MEDIA/'ffprobe.exe'),'-v','error','-select_streams','v:0',
        '-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(path)]))['frames']
    return streams,[float(f['best_effort_timestamp_time']) for f in frames]


def main():
    sources={'original':Path('E:/Media/avatar/lesser talking sad 03.mp4'),
        'four-three':ROOT/'out/ovda-expansion-fixtures/four-three-60.mp4',
        '1080':ROOT/'out/ovda-user-validation/86afad4c521147b492e052186b57a277/1080-hevc-audio.mp4',
        '4k':FOLDER/'4k30-audio.mp4',
        'cuts':ROOT/'out/live-action-evaluation/eab25eb5c4b948b2a11b5ce3dad79a2f/KnownCut/input.mp4'}
    rows=[]
    for name,source in sources.items():
        expected,pts=probe(source)
        for renderer in ('cpu','cuda'):
            output=FOLDER/f'{name}-{renderer}.mp4'
            actual,output_pts=probe(output)
            assert len(pts)==len(output_pts)>0
            delta=max(abs((a-pts[0])-(b-output_pts[0])) for a,b in zip(pts,output_pts))
            assert delta<=.0001
            src_video=next(s for s in expected if s['codec_type']=='video')
            out_video=next(s for s in actual if s['codec_type']=='video')
            assert Fraction(src_video['avg_frame_rate'])==Fraction(out_video['avg_frame_rate'])
            audio=[s for s in expected if s['codec_type']=='audio']
            out_audio=[s for s in actual if s['codec_type']=='audio']
            assert len(audio)==len(out_audio)
            for a,b in zip(audio,out_audio):
                assert a['sample_rate']==b['sample_rate'] and a['channels']==b['channels']
                assert abs(float(a['duration'])-float(b['duration']))<=.05
            rows.append(dict(name=name,renderer=renderer,frames=len(pts),max_relative_pts_error=delta,audio=bool(audio)))
    from depthsbs_app.resources import configure_media_tools
    from depthsbs_app.pipeline import probe_video
    from evaluate_depth_models import inspect_media
    configure_media_tools(MEDIA)
    inspect_media(FOLDER/'user-cuda-original.mp4',probe_video(sources['original']))
    (FOLDER/'timing-report.json').write_text(json.dumps(dict(passed=True,rows=rows,user_launcher_decode_audio=True),indent=2))
    print('PASS 10 outputs: exact cadence, relative PTS, audio channels/rate/duration; user launcher full decode')


if __name__=='__main__':main()
