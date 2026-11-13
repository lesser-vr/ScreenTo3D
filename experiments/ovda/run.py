# Optional personal non-commercial oVDA runner; NC-SA-UHDV1.0.
import argparse
import json
from pathlib import Path
from oracle import ROOT


def main():
    parser=argparse.ArgumentParser(description='Personal non-commercial oVDA c16 TensorRT preview, max 124 frames; not the standard app.')
    parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    from screento3d_app import pipeline
    from screento3d_app.resources import configure_media_tools
    from screento3d_app.depth_backend import BackendSpec,BackendBinding
    from vda_comparison import BoundedEngine,validate_metadata
    from trt_engine import OvdaTrt
    configure_media_tools(ROOT/'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal/ffmpeg')
    meta=pipeline.probe_video(args.input)
    validate_metadata(meta,124)
    if not meta['total_frames'] or abs(meta['width']/meta['height']-16/9)>.001:
        raise ValueError('Experimental oVDA launcher requires known frame count <=124 and standard 16:9; no implicit crop/padding')
    if args.output.exists():raise ValueError('Choose a new output path; preview does not overwrite existing files')
    binding=BackendBinding(BackendSpec('ovda-small-c16','tensorrt-fp32-experiment',True,True),
        lambda p:BoundedEngine(OvdaTrt(p),124),lambda f:f)
    print('oVDA c16 TensorRT FP32 / NC-SA-UHDV1.0 / personal non-commercial experiment',flush=True)
    result=pipeline.convert_video(args.input,args.output,'video-quality',lambda e:print(json.dumps(e),flush=True),
                                  depth_backend=binding)
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
