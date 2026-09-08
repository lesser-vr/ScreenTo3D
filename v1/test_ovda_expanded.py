"""4:3/1080p/4K oVDA CPU-CUDA parity, media and cleanup gate."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import uuid
from unittest.mock import patch
from depthsbs_app import pipeline, ovda, local_projection
from depthsbs_app.main import build_parser, run_worker
from depthsbs_app.resources import configure_media_tools
from evaluate_depth_models import inspect_media, sha

ROOT=Path(__file__).resolve().parents[1]
MEDIA=ROOT/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg'
RUNTIME=Path('C:/TensorRT/TensorRT-11.2.1.2/bin')


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--original',type=Path,required=True);args=parser.parse_args()
    root=ROOT/'out/ovda-expanded-gate'/uuid.uuid4().hex;root.mkdir(parents=True)
    print(root,flush=True)
    configure_media_tools(MEDIA)
    public_1080=root/'public-1080-hevc-audio.mp4'
    subprocess.run([str(MEDIA/'ffmpeg.exe'),'-hide_banner','-loglevel','error','-nostdin',
        '-i',str(args.original),'-f','lavfi','-i','sine=frequency=440:sample_rate=48000',
        '-t','1','-c:v','libx265','-preset','fast','-x265-params','log-level=error',
        '-c:a','aac','-shortest',str(public_1080)],check=True)
    fourk=root/'4k30-audio.mp4'
    subprocess.run([str(MEDIA/'ffmpeg.exe'),'-hide_banner','-loglevel','error','-nostdin',
        '-f','lavfi','-i','testsrc2=size=3840x2160:rate=30','-f','lavfi','-i','sine=frequency=440:sample_rate=48000',
        '-t','1','-c:v','libx265','-preset','fast','-x265-params','log-level=error','-c:a','aac','-shortest',str(fourk)],check=True)
    sources=[('original',args.original,'h264'),
             ('four-three',ROOT/'out/ovda-expansion-fixtures/four-three-60.mp4','h264'),
             ('1080',public_1080,'hevc'),
             ('4k',fourk,'hevc'),
             ('cuts',ROOT/'out/live-action-evaluation/eab25eb5c4b948b2a11b5ce3dad79a2f/KnownCut/input.mp4','h264')]
    report=dict(passed=False,clips=[],failures=[],rejections=[])
    def arguments(source,output,codec,renderer):
        return build_parser().parse_args(['--worker','--depth-backend','ovda-small-c16','--ovda-noncommercial',
            '--ovda-engine-dir',str(ROOT/'out/ovda-local'),'--runtime-dir',str(RUNTIME),
            '--input',str(source),'--output',str(output),'--output-codec',codec,
            '--mode','video-quality','--stereo-renderer',renderer,'--frame-hashes','--status-file',str(output.with_suffix('.jsonl'))])
    try:
        for name,source,codec in sources:
            results={}
            for renderer in ('cpu','cuda'):
                output=root/f'{name}-{renderer}.mp4'
                # App inference must not import the upstream source or checkpoint.
                engine_cls=ovda.runtime_class()
                package=engine_cls.__module__.rsplit('.',1)[0]
                with patch(package+'.oracle.upstream',side_effect=AssertionError('Runtime imported build-only source')):
                    assert run_worker(arguments(source,output,codec,renderer))==0, output
                events=[json.loads(line) for line in output.with_suffix('.jsonl').read_text(encoding='utf-8').splitlines()]
                complete=[e for e in events if e['event']=='complete'];assert len(complete)==1
                result=complete[0]
                inspect_media(output,pipeline.probe_video(source,codec))
                streams=json.loads(subprocess.check_output([str(MEDIA/'ffprobe.exe'),'-v','error','-show_streams','-of','json',str(output)]))['streams']
                video=next(s for s in streams if s['codec_type']=='video')
                assert video['codec_name']==codec
                if renderer=='cuda':
                    stats=result['telemetry']['stereo']['projection_resources']
                    assert stats['completed_eye_calls']==result['frames']*2
                results[renderer]=result
            assert results['cpu']['telemetry']['diagnostic_hashes']==results['cuda']['telemetry']['diagnostic_hashes']
            if name=='original':
                prior=json.loads((ROOT/'out/ovda-expansion-evaluation/d6595c357e654ebfb6fba313845cbf9e/quality-ovda.json').read_text())
                assert prior['telemetry']['diagnostic_hashes']==results['cuda']['telemetry']['diagnostic_hashes']
            if name=='cuts':assert results['cuda']['telemetry']['scene_cut_resets']==1
            report['clips'].append(dict(name=name,source_sha256=sha(source),results=results))
            print('PASS exact CPU/CUDA '+name,flush=True)
        # Both depth and projection must be closed before failed jobs return.
        for name,source,codec in (sources[1],sources[3]):
            for kind in ('cancel','depth_failure','projection_failure'):
                backend=ovda.binding(ROOT/'out/ovda-local',RUNTIME,True);factory=backend.engine_factory
                depths=[]; projections=[]
                def depth_factory(progress):
                    engine=factory(progress);depths.append(engine)
                    if kind=='depth_failure':
                        infer=engine.infer
                        def fail(frame):
                            if engine.calls==2:raise RuntimeError('injected depth_failure')
                            return infer(frame)
                        engine.infer=fail
                    return engine
                def projection_factory(w,h):
                    engine=local_projection.factory(w,h);projections.append(engine)
                    if kind=='projection_failure':
                        project=engine.project
                        def fail(*a,**kw):
                            if engine.calls==2:raise RuntimeError('injected projection_failure')
                            return project(*a,**kw)
                        engine.project=fail
                    return engine
                output=root/f'{name}-{kind}-preserved.mp4';sentinel=b'existing output';output.write_bytes(sentinel)
                cancel=root/f'{name}.cancel'
                def progress(event):
                    if kind=='cancel' and event.get('event')=='progress' and event['frame']>=1:cancel.touch()
                try:
                    pipeline.convert_video(source,output,'video-quality',progress,cancel if kind=='cancel' else None,
                        depth_backend=replace(backend,engine_factory=depth_factory),projection_factory=projection_factory,output_codec=codec)
                except (RuntimeError,InterruptedError) as error:
                    assert (kind=='cancel' and isinstance(error,InterruptedError)) or ('injected '+kind in str(error))
                else:raise AssertionError('Abort expected')
                assert output.read_bytes()==sentinel
                assert len(depths)==len(projections)==1
                assert depths[0].closed and not depths[0].cache and depths[0].context is None
                assert not projections[0].handle.value
                report['failures'].append(dict(source=name,kind=kind,passed=True))
        output=root/'4k-h264-preserved.mp4';output.write_bytes(b'preserve')
        with patch.object(ovda,'runtime_class',side_effect=AssertionError('GPU loaded before geometry rejection')):
            assert run_worker(arguments(fourk,output,'h264','cuda'))==1
        assert output.read_bytes()==b'preserve'
        report['rejections'].append('4K H264 before GPU/output mutation')
        report['passed']=True
    finally:
        (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(root/'report.json',flush=True)


if __name__=='__main__':main()
