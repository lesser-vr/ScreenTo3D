"""Owned public WGC -> Small native Half TB proof, followed by Torch-path parity."""
import argparse
from contextlib import ExitStack
from dataclasses import replace
import importlib.abc
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent));sys.path.insert(0,str(ROOT/'v1'))


def baseline(args):
    import numpy as np
    from evaluate_sbs_quality import open_session,Session
    from depthsbs_app.desktop_jobs import BUNDLE
    from depthsbs_app.resources import configure_resource_root
    configure_resource_root(BUNDLE)
    with np.load(args.output/'native.npz',allow_pickle=False) as source:
        inputs,expected=source['inputs'],source['outputs']
    h,w=inputs.shape[1:3];rows=[]
    with ExitStack() as stack:
        backend,owner,post,policy=open_session(stack,'da2-small',w,h,'half-tb',False)
        session=Session(backend,owner,post,policy,'da2-small')
        for index,rgb in enumerate(inputs):
            actual,_,_=session.frame(rgb,index)
            delta=np.abs(actual.astype(np.int16)-expected[index].astype(np.int16))
            rows.append(dict(frame=index,max_difference=int(delta.max()),mean_difference=float(delta.mean())))
    result=dict(passed=all(r['max_difference']==0 for r in rows),frames=rows,
        scope='Same captured RGB, Small engine, default .5 detail policy, 60Hz fixture clock; no static reuse or FPS claim')
    (args.output/'parity.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    assert result['passed'],'Native/Torch rendered pixels differ'


def native(args):
    class NoTorch(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            if fullname.split('.')[0]=='torch':raise ImportError('The native GPU probe forbids Torch')
    sys.meta_path.insert(0,NoTorch())
    import numpy as np
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QPainter,QColor
    from PySide6.QtWidgets import QApplication,QWidget
    from depthsbs_app.desktop_jobs import BUNDLE
    from depthsbs_app.resources import configure_resource_root
    from depthsbs_app.live_policy import resolve_live
    from depthsbs_app.live_model import model_adapter
    configure_resource_root(BUNDLE)
    from native_buffers import Owner,Capture,Renderer
    app=QApplication.instance() or QApplication([])
    class Source(QWidget):
        def __init__(self):
            super().__init__();self.setWindowTitle('ScreenTo3D owned native GPU proof');self.resize(640,360);self.x=0
            self.timer=QTimer(self);self.timer.timeout.connect(self.advance);self.timer.start(33)
        def advance(self):self.x=(self.x+7)%500;self.update()
        def paintEvent(self,event):
            painter=QPainter(self);painter.fillRect(self.rect(),QColor('#304457'));painter.fillRect(self.x,60,100,220,QColor('#e5bd75'));painter.end()
    source=Source();source.move(80,80);source.show()
    def pump():app.processEvents();time.sleep(.004)
    for _ in range(80):pump()
    selected=dict(kind='window',id=int(source.winId()),pid=os.getpid(),label=source.windowTitle(),
        width=round(source.width()*source.devicePixelRatioF()),height=round(source.height()*source.devicePixelRatioF()))
    args.output.mkdir(parents=True,exist_ok=False);inputs=[];outputs=[];renderer=capture=None
    try:
        with Owner() as owner:
            try:
                capture=Capture(selected,owner);deadline=time.monotonic()+10;bgra=None
                while bgra is None and time.monotonic()<deadline:pump();bgra=capture.read()
                assert bgra is not None,'Owned WGC source did not publish a frame'
                h,w,_=bgra.shape
                policy=model_adapter('da2-small').apply_live_policy(replace(resolve_live('performance',.5),depth_backend='da2-small',stereo_layout='half-tb'))
                renderer=Renderer(w,h,policy,owner);renderer.configure_live_quality('detail')
                for index in range(args.frames):
                    if index:
                        bgra=None;deadline=time.monotonic()+10
                        while bgra is None and time.monotonic()<deadline:pump();bgra=capture.read()
                        assert bgra is not None
                    frame=renderer.frame(bgra)
                    # Full-frame readbacks below are diagnostic parity fixtures,
                    # not a proposed capture transport or performance measurement.
                    inputs.append(frame.to_host().copy())
                    scene=renderer.inspect_scene(frame);depth=renderer.infer(frame)
                    renderer.source_ns=1_000_000_000+round(index*1e9/60);renderer.slot=index%2
                    slot=renderer.render(frame,depth,scene=scene)
                    pixels=np.empty((renderer.pool.height,renderer.pool.width,4),np.uint8)
                    renderer.pool.check(renderer.pool.dll.live_pool_readback(renderer.pool.handle,slot,pixels.ctypes.data))
                    outputs.append(pixels)
                buffer=renderer.rgb;renderer.close();renderer=None
                try:buffer.data_ptr()
                except RuntimeError:expired_rejected=True
                else:expired_rejected=False
                assert expired_rejected
            finally:
                if renderer:renderer.close()
                if capture:capture.close()
        assert not any(name=='torch' or name.startswith('torch.') for name in sys.modules)
        np.savez_compressed(args.output/'native.npz',inputs=np.stack(inputs),outputs=np.stack(outputs))
        report=dict(passed=True,torch_imported=False,source='Owned generated WGC window only',frames=len(inputs),
            shape=[w,h],output_shape=list(outputs[0].shape),expired_buffer_rejected=expired_rejected,
            path='WGC CUDA copy -> native BGRA/RGB -> native Small preprocessing -> TensorRT -> existing detail post -> native Half TB pool',
            scope='Small prototype, diagnostic readbacks for parity; no app integration, other-model parity, Qt output presentation or FPS claim')
        (args.output/'native.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
    finally:source.timer.stop();source.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline',action='store_true');parser.add_argument('--frames',type=int,default=16)
    args=parser.parse_args();args.output=args.output.resolve()
    if args.baseline:baseline(args)
    else:native(args)
