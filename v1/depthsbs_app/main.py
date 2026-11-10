import argparse
import json
import sys
import traceback
from pathlib import Path

from . import __version__
from .config import DEFAULT_MODE_MODELS, MODES, OUTPUTS, validate_mode_model
from .error_reporting import error_event


def emitter(status_file: Path | None):
    def emit(event: dict) -> None:
        line = json.dumps(event, ensure_ascii=False)
        if status_file is not None:
            status_file.parent.mkdir(parents=True, exist_ok=True)
            with status_file.open("a", encoding="utf-8") as output:
                output.write(line + "\n")
        elif sys.stdout is not None:
            print(line, flush=True)
    return emit


def run_worker(arguments, gpu_preview=False) -> int:
    emit = emitter(arguments.status_file)
    try:
        validate_mode_model(arguments.mode, arguments.depth_backend)
        from .pipeline import convert_video
        options = {'output_codec': getattr(arguments, 'output_codec', 'h264')}
        options['stereo_layout'] = getattr(arguments, 'stereo_layout', 'full-sbs')
        if getattr(arguments, 'depth_backend', 'da2-small') == 'ovda-small-c16':
            from .ovda import binding, LICENSE_NOTICE
            options['depth_backend'] = binding(arguments.ovda_engine_dir, arguments.runtime_dir, arguments.ovda_noncommercial)
            options['depth_backend'].validate_policy(MODES[arguments.mode])
            emit({'event': 'depth_backend', **options['depth_backend'].describe(), 'license_notice': LICENSE_NOTICE, 'fallback': False})
        if getattr(arguments, 'depth_backend', 'da2-small') == 'da2-base':
            from .da2_base import binding
            options['depth_backend'] = binding(arguments.da2_base_engine_dir, arguments.runtime_dir)
            emit({'event': 'depth_backend', 'model_id': 'da2-base', 'runtime': options['depth_backend'].spec.runtime, 'weight_license': 'CC-BY-NC-4.0'})
        if getattr(arguments, 'letterbox_refinement', False):
            options['letterbox_refinement'] = True
            emit({'event': 'letterbox_refinement', 'enabled': True, 'experimental': True})
        if getattr(arguments, 'depth_backend', 'da2-small') == 'vda-small':
            if arguments.vda_engine_dir is None:
                raise ValueError('VDA requires --vda-engine-dir built by build_vda_artifact.py')
            from .depth_backend import vda_binding, vda_offline_binding
            create_binding = vda_offline_binding if arguments.mode == 'offline-quality' else vda_binding
            options['depth_backend'] = create_binding(arguments.vda_engine_dir, arguments.runtime_dir)
            options['depth_backend'].validate_policy(MODES[arguments.mode])
            emit({'event': 'depth_backend', 'model_id': 'vda-small', 'runtime': options['depth_backend'].spec.runtime,
                  'processing': options['depth_backend'].spec.processing,
                  'preview': True, 'fallback': False})
        selected_renderer = getattr(arguments, 'stereo_renderer', None)
        if gpu_preview and selected_renderer is not None:
            raise ValueError('--stereo-renderer is source-app only; GPU preview uses --reference-cpu for comparison')
        if selected_renderer == 'cuda':
            from .local_projection import factory
            options['projection_factory'] = factory
            emit({'event': 'renderer', 'algorithm': 'forward_zbuffer_cuda_local', 'cpu_fallback': False})
        elif gpu_preview and selected_renderer is None and not getattr(arguments, 'reference_cpu', False):
            from .gpu_preview import preview_factory
            options['projection_factory'] = preview_factory
            emit({'event': 'renderer', 'algorithm': 'forward_zbuffer_cuda_preview',
                  'experimental': True, 'cpu_fallback': False})
        if getattr(arguments, 'reference_cpu', False):
            if not gpu_preview:
                raise ValueError('--reference-cpu is only available in the GPU preview')
            emit({'event': 'renderer', 'algorithm': 'forward_zbuffer_cpu',
                  'explicit_reference': True, 'cpu_fallback': False})
        if getattr(arguments, 'frame_hashes', False):
            options['diagnostic_hashes'] = True
        convert_video(
            arguments.input, arguments.output, arguments.mode, emit, arguments.cancel_file,
            **options
        )
        return 0
    except InterruptedError as error:
        if getattr(error, '__notes__', None):
            emit(error_event(error, detailed=getattr(arguments, 'detailed_errors', False)))
            return 1
        return 2
    except BaseException as error:
        emit(error_event(error, detailed=getattr(arguments, 'detailed_errors', False)))
        if getattr(arguments, 'detailed_errors', False) and sys.stderr is not None:
            traceback.print_exc(file=sys.stderr)
        return 1


class ProductArgumentParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        parsed = super().parse_args(args, namespace)
        if parsed.depth_backend is None:
            parsed.depth_backend = DEFAULT_MODE_MODELS[parsed.mode]
        return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = ProductArgumentParser(prog="ScreenTo3D")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--detailed-errors", action="store_true", help="Include private error details and tracebacks; off by default")
    parser.add_argument('--check-installation', action='store_true', help='Read-only oVDA installation report without loading model engines')
    parser.add_argument('--reference-cpu', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--frame-hashes', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--letterbox-refinement', action='store_true', help='Experimental black-bar backdrop refinement (off by default)')
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=tuple(MODES), default="balanced")
    parser.add_argument('--output-codec', choices=tuple(OUTPUTS), default='h264')
    parser.add_argument('--stereo-layout', choices=('full-sbs', 'half-sbs', 'full-tb', 'half-tb'), default='full-sbs')
    parser.add_argument('--stereo-renderer', choices=('cpu', 'cuda'), help='Explicit source-app stereo renderer; never automatic fallback')
    parser.add_argument('--depth-backend', choices=('da2-small', 'da2-base', 'vda-small', 'ovda-small-c16'))
    parser.add_argument('--ovda-engine-dir', type=Path, help='Trusted local oVDA profile directory')
    parser.add_argument('--ovda-noncommercial', action='store_true', help='Confirm personal/non-commercial oVDA use under NC-SA-UHDV1.0')
    parser.add_argument('--da2-base-engine-dir', type=Path)
    parser.add_argument('--vda-engine-dir', type=Path, help='Trusted locally built VDA artifact directory')
    parser.add_argument('--runtime-dir', type=Path, help='Explicit TensorRT runtime DLL directory for VDA')
    parser.add_argument('--media-tools', type=Path, help='Directory containing ffmpeg.exe and ffprobe.exe')
    parser.add_argument("--status-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--cancel-file", type=Path, help=argparse.SUPPRESS)
    return parser


def main(gpu_preview=False) -> int:
    arguments = build_parser().parse_args()
    if arguments.check_installation:
        if arguments.depth_backend != 'ovda-small-c16' or arguments.worker or arguments.diagnostics:
            raise SystemExit('--check-installation requires oVDA and cannot be combined with conversion/diagnostics')
        from .ovda_installation import installation_report
        report = installation_report(arguments.ovda_engine_dir, arguments.runtime_dir, arguments.media_tools, arguments.stereo_renderer or 'cpu')
        emitter(arguments.status_file)({'event': 'installation', **report})
        return 0 if report['ready'] else 1
    if arguments.media_tools is not None:
        from .resources import configure_media_tools
        configure_media_tools(arguments.media_tools)
    if arguments.status_file is not None:
        arguments.status_file.unlink(missing_ok=True)
    if arguments.cancel_file is not None:
        arguments.cancel_file.unlink(missing_ok=True)
    if arguments.diagnostics:
        emit = emitter(arguments.status_file)
        try:
            if arguments.stereo_renderer == 'cuda':
                from .local_projection import factory
                with factory(2, 2) as projection:
                    emit({'event': 'renderer_diagnostics', 'algorithm': projection.algorithm, 'resources': projection.telemetry()})
            if arguments.depth_backend == 'ovda-small-c16':
                from .ovda import binding, profiles
                if not arguments.ovda_noncommercial:
                    raise ValueError('oVDA diagnostics require --ovda-noncommercial; read experiments/ovda/LICENSE')
                for directory in profiles(arguments.ovda_engine_dir).values():
                    backend = binding(directory, arguments.runtime_dir, True)
                    with backend.engine_factory(emit) as engine:
                        emit({'event': 'diagnostics', 'depth_backend': backend.describe(), 'resources': engine.telemetry()})
                return 0
            if arguments.depth_backend == 'da2-base':
                from .da2_base import binding, profiles
                for directory in profiles(arguments.da2_base_engine_dir).values():
                    backend = binding(directory, arguments.runtime_dir)
                    with backend.engine_factory(emit) as engine:
                        emit({'event': 'diagnostics', 'depth_backend': backend.describe(), 'resources': engine.telemetry()})
                return 0
            if arguments.depth_backend == 'vda-small':
                from .depth_backend import vda_binding, vda_offline_binding
                if arguments.vda_engine_dir is None:
                    raise ValueError('VDA diagnostics require --vda-engine-dir')
                from .vda_artifacts import artifact_profiles
                create_binding = vda_offline_binding if arguments.mode == 'offline-quality' else vda_binding
                for directory in artifact_profiles(arguments.vda_engine_dir).values():
                    backend = create_binding(directory, arguments.runtime_dir)
                    with backend.engine_factory(emit) as engine:
                        emit({'event': 'diagnostics', 'depth_backend': backend.describe(), 'resources': engine.telemetry()})
                return 0
            from .trt_backend import diagnostics
            if gpu_preview:
                from .gpu_preview import preview_factory
                with preview_factory(2, 2):
                    pass
            emit({"event": "diagnostics", **diagnostics()})
            return 0
        except BaseException as error:
            emit(error_event(error, detailed=arguments.detailed_errors))
            return 1
    if arguments.worker:
        if arguments.input is None or arguments.output is None:
            raise SystemExit("--worker requires --input and --output")
        return run_worker(arguments, gpu_preview=gpu_preview)
    validate_mode_model(arguments.mode, arguments.depth_backend)
    from .gui import run_gui
    run_gui(gpu_preview=gpu_preview, backend=arguments.depth_backend,
            engine_dir={'da2-base': arguments.da2_base_engine_dir, 'vda-small': arguments.vda_engine_dir, 'ovda-small-c16': arguments.ovda_engine_dir}.get(arguments.depth_backend),
            runtime_dir=arguments.runtime_dir, media_tools=arguments.media_tools, mode=arguments.mode,
            letterbox_refinement=arguments.letterbox_refinement, stereo_renderer=arguments.stereo_renderer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
