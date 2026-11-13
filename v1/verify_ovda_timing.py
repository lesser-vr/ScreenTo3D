"""Postdecode timing/audio checks for the recorded expansion matrix."""
from fractions import Fraction
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
MEDIA=ROOT/'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal/ffmpeg'
FOLDER=ROOT/'out/ovda-public-timing'


def probe(path):
    streams=json.loads(subprocess.check_output([str(MEDIA/'ffprobe.exe'),'-v','error','-show_streams','-of','json',str(path)]))['streams']
    frames=json.loads(subprocess.check_output([str(MEDIA/'ffprobe.exe'),'-v','error','-select_streams','v:0',
        '-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(path)]))['frames']
    return streams,[float(f['best_effort_timestamp_time']) for f in frames]


def main():
    sources={'original':ROOT/'out/public-live-default/FloorballGame.mp4',
        'four-three':ROOT/'out/public-live-default/OfficeWalk.mp4',
        '1080':ROOT/'out/public-live-default/FloorballGame.mp4',
        '4k':FOLDER/'4k30-audio.mp4',
        'cuts':ROOT/'out/public-live-default/ParkingGarage.mp4'}
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
    from screento3d_app.resources import configure_media_tools
    from screento3d_app.pipeline import probe_video
    from evaluate_depth_models import inspect_media
    configure_media_tools(MEDIA)
    inspect_media(FOLDER/'original-cuda.mp4',probe_video(sources['original']))
    (FOLDER/'timing-report.json').write_text(json.dumps(dict(passed=True,rows=rows,launcher_decode_audio=True),indent=2))
    print('PASS 10 outputs: exact cadence, relative PTS, audio channels/rate/duration; launcher full decode')


if __name__=='__main__':main()
