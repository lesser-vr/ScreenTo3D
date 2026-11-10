"""Owned GPU-rendered mpv source for genuine public UVG 120fps clips."""
import ctypes as ct
from ctypes import wintypes as wt
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
MEDIA = ROOT/'out/public-hfr'
PLAYER_SHA256='2f99a693ef2f8eefa4ae36db22cdab5fac1a5eec24c9b591fbe2bf364cbcddf8'
CLIP_SHA256={
    'Jockey':'36609adcf8d36db4c842003ebfa661fc03f9ad4bb750bd889ea52aab6651831c',
    'Beauty':'ad705b937081ad4e62faa68a30c4d30a06a18b81410996b24b01a4fd9119b39c',
}

class Source:
    def __init__(self, clip, log):
        if clip not in ('Jockey','Beauty'):
            raise ValueError('Only the explicitly prepared public clips are allowed')
        self.process=None
        self.log=None
        self.path=MEDIA/f'{clip}-120.mp4'
        self.probe=json.loads(subprocess.check_output([shutil.which('ffprobe'),'-v','error','-select_streams','v:0',
            '-show_entries','stream=width,height,avg_frame_rate,nb_frames:format=duration','-of','json',str(self.path)]))
        stream=self.probe['streams'][0]
        if (stream['width'],stream['height'],stream['avg_frame_rate'],stream['nb_frames'])!=(3840,2160,'120/1','600'):
            raise ValueError('Unvalidated public HFR geometry/rate/count')
        self.sha256=hashlib.sha256(self.path.read_bytes()).hexdigest()
        if self.sha256!=CLIP_SHA256[clip]:raise ValueError('Public clip hash changed')
        player=MEDIA/'mpv/mpv.exe'
        if hashlib.sha256(player.read_bytes()).hexdigest()!=PLAYER_SHA256:raise ValueError('Player hash changed')
        from depthsbs_app.capture_sources import enable_capture_dpi
        enable_capture_dpi()
        self.command=[str(player),'--no-config','--no-audio','--loop-file=inf',
                      '--hwdec=d3d11va','--vo=gpu','--gpu-api=d3d11','--d3d11-sync-interval=0',
                      '--video-sync=audio','--interpolation=no','--no-border','--ontop',
                      '--geometry=3840x2160+0+0','--hidpi-window-scale=no','--no-osc','--osd-level=0',
                      f'--title=DepthSBS owned UVG 120fps {clip}',str(self.path)]
        try:
            self.log=Path(log).open('wb')
            self.process=subprocess.Popen(self.command,stdout=self.log,stderr=self.log,
                                          creationflags=subprocess.CREATE_NO_WINDOW)
            user=ct.WinDLL('user32')
            user.GetWindowThreadProcessId.argtypes=[wt.HWND,ct.POINTER(wt.DWORD)]
            user.IsWindowVisible.argtypes=[wt.HWND]
            enum=ct.WINFUNCTYPE(wt.BOOL,wt.HWND,wt.LPARAM)
            def find(hwnd,_):
                pid=wt.DWORD();user.GetWindowThreadProcessId(hwnd,ct.byref(pid))
                if pid.value==self.process.pid and user.IsWindowVisible(hwnd):
                    found.append(int(hwnd))
                return True
            callback=enum(find)
            end=time.monotonic()+20
            previous=[];stable_since=time.monotonic()
            while time.monotonic()<end:
                found=[];user.EnumWindows(callback,0)
                if found!=previous:stable_since=time.monotonic();previous=found
                if found and time.monotonic()-stable_since>=3:break
                if self.process.poll() is not None:raise RuntimeError('Owned player exited; inspect its log')
                time.sleep(.05)
            if not found:raise TimeoutError('Owned player window missing')
            self.hwnd=found[0]
            user.SetWindowPos.argtypes=[wt.HWND,wt.HWND,ct.c_int,ct.c_int,ct.c_int,ct.c_int,wt.UINT]
            # Do not synchronously wait across GUI threads while Qt's owner is busy.
            if not user.SetWindowPos(self.hwnd,-1,0,0,3840,2160,0x4050):raise ct.WinError()
            self.source=dict(kind='window',id=self.hwnd,pid=self.process.pid,label=f'Owned UVG {clip} 120fps',width=3840,height=2160)
        except BaseException:
            self.close();raise

    def close(self):
        if self.process is not None and self.process.poll() is None:
            user=ct.WinDLL('user32');user.PostMessageW.argtypes=[wt.HWND,wt.UINT,wt.WPARAM,wt.LPARAM]
            if hasattr(self,'hwnd'):user.PostMessageW(self.hwnd,0x0010,0,0)
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate();self.process.wait(timeout=5)
        if self.log:self.log.close()

def preflight(clip):
    import torch
    from depthsbs_app.gpu_capture import GpuCapture
    from depthsbs_app.capture_sources import validate_source
    output=MEDIA/f'{clip}-source-preflight-mpv.json'
    report=dict(completed=False,clip=clip)
    source=None
    try:
        source=Source(clip,MEDIA/f'{clip}-source-preflight-mpv.log')
        report.update(file_sha256=source.sha256,probe=source.probe,command=source.command)
        time.sleep(1)
        validate_source(source.source)
        stream=torch.cuda.Stream()
        with GpuCapture(source.source,False,torch.cuda.current_device()) as capture:
            began=time.perf_counter();stamps=[];hashes=[];sequences=[];first_shape=None
            while time.perf_counter()-began<10:
                frame=capture.read(stream)
                if frame is None:time.sleep(.0005);continue
                image,info=frame
                with torch.cuda.stream(stream):
                    sample=image[::24,::24,:3].contiguous().cpu().numpy()
                stamps.append(info['source_ns']);sequences.append(info['sequence'])
                hashes.append(hashlib.sha256(sample.tobytes()).hexdigest())
                first_shape=tuple(image.shape)
            elapsed=time.perf_counter()-began
        changes=sum(a!=b for a,b in zip(hashes,hashes[1:]))
        report.update(completed=True,seconds=elapsed,captured=len(hashes),distinct_samples=len(set(hashes)),
                      changed_frames_per_second=changes/elapsed,capture_fps=len(hashes)/elapsed,
                      callback_sequence_rate=(sequences[-1]-sequences[0])/elapsed,shape=first_shape,
                      source_timestamp_monotonic=all(a<b for a,b in zip(stamps,stamps[1:])))
    except BaseException as exc:
        report['error']=repr(exc);raise
    finally:
        if source:source.close()
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))

if __name__=='__main__':
    import sys
    preflight(sys.argv[1])
