# oVDA runtime validation, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Allocation, reset and nonfinite failure checks; not native FPS evidence."""
import argparse
import json
from pathlib import Path
import threading
import cv2
import torch
from screento3d_app.gpu_frame import GpuFrame
from public_test_media import CORPUS
from trial_runtime import create_engine, selected, RUNTIME
from runtime_trial import reference_class


def frame_for(engine,rgb):
    with torch.cuda.stream(engine.stream):
        return GpuFrame(torch.from_numpy(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGRA)).to(engine.device),engine)


def pointers(engine):
    buffers=engine._buffers
    return [v.data_ptr() for v in (buffers.image,*buffers.outputs.values(),
            *(v for row in buffers.schedules for v in row),*engine.cache.values())]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    cap=cv2.VideoCapture(str(CORPUS/'FloorballGame.mp4'))
    ok,bgr=cap.read();cap.release()
    if not ok:raise ValueError('Missing public source')
    rgb=cv2.cvtColor(cv2.resize(bgr,(1280,720)),cv2.COLOR_BGR2RGB)
    report=dict(allocations=[],rejections=[],scope='Torch allocation peaks exclude TensorRT/native allocations; isolated inference')
    def rejected(name,error,operation):
        try:operation()
        except error:report['rejections'].append(name)
        else:raise AssertionError('Missing rejection: '+name)
    try:
        for variant in ('before','after'):
            if variant=='before':
                with selected('fp32-current') as directory:
                    engine=reference_class()(directory=directory,runtime_dir=RUNTIME)
            else:engine=create_engine('fp32-current')
            try:
                frame=frame_for(engine,rgb)
                for _ in range(18):
                    token=engine.infer_device(frame);engine.complete_device(token);token=None
                stable=pointers(engine) if variant=='after' else None
                peaks=[]
                for _ in range(6):
                    torch.cuda.reset_peak_memory_stats(engine.device)
                    before=torch.cuda.memory_allocated(engine.device)
                    token=engine.infer_device(frame)
                    engine.complete_device(token)
                    peaks.append(torch.cuda.max_memory_allocated(engine.device)-before)
                    token=None
                    if stable is not None:assert stable==pointers(engine)
                telemetry=engine.telemetry()
                report['allocations'].append(dict(variant=variant,steady_inference_peak_delta_bytes=peaks,
                                                 cache_bytes=telemetry['cache_bytes'],
                                                 fixed_buffer_bytes=telemetry.get('fixed_inference_buffer_bytes',0)))
                if variant=='after':
                    assert telemetry['output_validation_waits']==engine.calls
                    assert telemetry['cache_bank_count']==1
                    for reason in ('start','scene_cut','source_change','discontinuity'):
                        engine.reset(reason)
                        assert stable==pointers(engine) and engine.used==0 and engine.shape is None
                        with torch.cuda.stream(engine.stream):
                            assert all(int(torch.count_nonzero(v))==0 for v in engine.cache.values())
                        token=engine.infer_device(frame);engine.complete_device(token);token=None
                    rejected('invalid reset',ValueError,lambda:engine.reset('unknown'))
                    token=engine.infer_device(frame)
                    failures=[]
                    def close_foreign():
                        try:engine.close()
                        except RuntimeError:failures.append(True)
                    thread=threading.Thread(target=close_foreign);thread.start();thread.join()
                    assert failures==[True] and not engine.closed and engine.pending_device is token
                    report['rejections'].append('foreign close preserves pending token')
                    engine.complete_device(token)
                    rejected('completed token',RuntimeError,token.validate)
                    buffers=engine._buffers
                    rejected('foreign validation stream',RuntimeError,buffers.check_outputs)
                    rejected('foreign cache stream',RuntimeError,buffers.shift_caches)
                    with torch.inference_mode(),torch.cuda.stream(engine.stream):
                        for name,value in buffers.outputs.items():
                            last=value.view(-1)[-1]
                            saved=last.clone()
                            for label,bad in (('NaN',float('nan')),('+Inf',float('inf')),('-Inf',float('-inf'))):
                                last.fill_(bad)
                                rejected(name+' '+label,ValueError,buffers.check_outputs)
                                last.copy_(saved)
                        buffers.check_outputs()
            finally:
                engine.close()
                assert engine.closed and engine.pending_device is None

        # End-to-end error handling must close the engine before lending output.
        engine=create_engine('fp32-current')
        context=engine.context
        class Poison:
            def __getattr__(self,name):return getattr(context,name)
            def execute_async_v3(self,stream):
                result=context.execute_async_v3(stream)
                engine._buffers.outputs['new_c4'].view(-1)[-1].fill_(float('nan'))
                return result
        try:
            frame=frame_for(engine,rgb)
            engine.context=Poison()
            rejected('nonfinite inference abort',ValueError,lambda:engine.infer_device(frame))
            assert engine.closed and engine.pending_device is None and engine.calls==0
            assert engine._buffers is None and engine._gpu_input is None
        finally:engine.close()

        # Host input uses the same persistent buffers and retains CPU parity.
        baseline=None;engine=create_engine('fp32-current')
        try:
            with selected('fp32-current') as directory:
                baseline=reference_class()(directory=directory,runtime_dir=RUNTIME)
            for _ in range(3):
                a,b=baseline.infer_device(rgb),engine.infer_device(rgb)
                baseline.stream.synchronize();engine.stream.synchronize()
                assert torch.equal(a.tensor,b.tensor)
                baseline.complete_device(a);engine.complete_device(b)
            report['host_depth_exact']=True
        finally:
            if baseline is not None:baseline.close()
            engine.close()
        report['passed']=True
    finally:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
