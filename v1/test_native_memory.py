"""Explicit worker-only CUDA ownership regression; never captures the desktop."""
import argparse
import json
from pathlib import Path
import threading
import numpy as np

def check():
    from screento3d_app.cuda_memory import Stream,Arena,Buffer
    stream=Stream();arena=Arena(stream);checks=[]
    try:
        old=arena.from_numpy(np.array([1,2,3],np.float32));pointer=old.data_ptr();old.close()
        value=arena.from_numpy(np.array([4,5,6],np.float32));assert value.data_ptr()==pointer
        try:old.data_ptr();raise AssertionError('Expired pointer accepted')
        except RuntimeError:checks.append('expired pointer rejected after pool reuse')
        failures=[]
        def foreign():
            try:value.data_ptr()
            except RuntimeError:failures.append(True)
        thread=threading.Thread(target=foreign);thread.start();thread.join();assert failures
        checks.append('foreign thread rejected')
        assert arena.finite([value]);value.upload(np.array([1,np.nan,3],np.float32));assert not arena.finite([value])
        checks.append('nonfinite result detected')
        for shape in [(0,),(-1,),(1024**3,),(1.5,),(True,)]:
            try:Buffer(arena,shape,np.float32);raise AssertionError('Invalid allocation accepted')
            except ValueError:pass
        checks.append('invalid allocation rejected')
        counts=[]
        for _ in range(100):
            temporary=arena.empty((32,32,3),np.uint8);temporary.close();counts.append(len(arena.allocations))
        assert len(set(counts))==1;checks.append('repeated allocation count plateaus')
    finally:arena.close();stream.close()
    try:value.data_ptr();raise AssertionError('Closed arena accepted')
    except RuntimeError:checks.append('closed arena rejected')
    return dict(passed=True,checks=checks,scope='Actual CUDA memory ownership; no capture, throughput or device-loss claim')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    from screento3d_app.resources import configure_resource_root
    from screento3d_app.desktop_jobs import BUNDLE
    configure_resource_root(BUNDLE)
    report=check();args.output.write_text(json.dumps(report,indent=2));print(json.dumps(report))
