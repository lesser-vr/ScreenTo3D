"""Read-only installation diagnostics, without importing/loading model engines."""
import importlib.metadata
from pathlib import Path
import subprocess
import sys


def installation_report(directory, runtime_dir, media_tools, renderer='cpu'):
    from .ovda import profiles, PROFILES, RUNTIME
    from .local_projection import checked_dll
    root=Path(__file__).resolve().parents[2]
    checks=[]
    def check(name,action,required=True):
        try:
            message=action()
            checks.append(dict(component=name,ready=True,required=required,message=str(message)))
        except Exception as error:
            checks.append(dict(component=name,ready=False,required=required,message=str(error)))
    def dependency(name,expected=None):
        version=importlib.metadata.version(name)
        if expected is not None and version!=expected:
            raise ValueError(f'{name} {version}; validated version is {expected}. Use the prepared oVDA Python environment.')
        return version
    def engines():
        installed=profiles(directory)
        shapes=', '.join(f'{h}x{w}' for h,w in installed)
        missing=set(PROFILES)-set(installed)
        return 'Verified '+shapes+' '+RUNTIME+('; additional profiles not installed: '+str(sorted(missing)) if missing else '')
    def runtime():
        if runtime_dir is None or not (Path(runtime_dir)/'nvinfer_11.dll').is_file():
            raise ValueError('TensorRT 11 DLLs missing; choose RuntimeDirectory containing nvinfer_11.dll')
        return 'TensorRT runtime DLL found; full Diagnostics verifies actual engine loading'
    def media():
        directory=Path(media_tools) if media_tools else root/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg'
        if not all((directory/f'{n}.exe').is_file() for n in ('ffmpeg','ffprobe')):
            raise ValueError('FFmpeg/FFprobe missing; prepare the local media tools')
        return 'FFmpeg and FFprobe found'
    def gpu():
        flags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0
        result=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version','--format=csv,noheader'],
                              capture_output=True,text=True,timeout=10,check=True,creationflags=flags)
        rows=result.stdout.strip().splitlines()
        # Runtime uses CUDA's current device, not a silently selected second GPU.
        if len(rows)!=1 or not rows[0].startswith('NVIDIA GeForce RTX 5090,'):
            raise ValueError('Validated configuration is a single RTX 5090; other/multiple GPU configurations require explicit build/device validation. Detected: '+result.stdout.strip())
        return rows[0]+'; driver 616.56 was tested; full Diagnostics verifies runtime capability'
    def optional_runtime():
        if not all((root/'experiments/ovda'/name).is_file() for name in ('__init__.py','trt_engine.py','preprocessing.py','LICENSE')):
            raise ValueError('Optional oVDA runtime source missing')
        return 'NC runtime and license present'
    check('engine profiles',engines)
    check('torch',lambda:dependency('torch','2.7.1+cu128'))
    check('TensorRT Python',lambda:dependency('tensorrt','11.2.1.2'))
    check('NumPy',lambda:dependency('numpy'))
    check('TensorRT DLLs',runtime)
    check('media tools',media)
    check('GPU',gpu)
    check('CUDA stereo',lambda:str(checked_dll().name)+' checksum verified',renderer=='cuda')
    check('optional runtime',optional_runtime)
    return dict(ready=all(c['ready'] for c in checks if c['required']),checks=checks,
                scope='Read-only local installation inventory, not an engine execution or performance gate',
                guidance='Use scripts/run-ovda.ps1 -Diagnostics -NonCommercial for actual load verification. No automatic downloads or fallback.')


def summary(report):
    return '\n'.join(('OK' if item['ready'] else 'MISSING / UNSUPPORTED')+': '+item['component']+' — '+item['message']
                     for item in report['checks'])
