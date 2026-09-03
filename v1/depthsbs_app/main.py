import argparse
import json
import sys
import traceback
from pathlib import Path

from . import __version__
from .config import MODES


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


def run_worker(arguments) -> int:
    emit = emitter(arguments.status_file)
    try:
        from .pipeline import convert_video
        convert_video(
            arguments.input, arguments.output, arguments.mode, emit, arguments.cancel_file
        )
        return 0
    except InterruptedError:
        return 2
    except BaseException as error:
        emit({"event": "error", "message": str(error), "type": type(error).__name__})
        if sys.stderr is not None:
            traceback.print_exc(file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="DepthSBS")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=tuple(MODES), default="balanced")
    parser.add_argument("--status-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--cancel-file", type=Path, help=argparse.SUPPRESS)
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    if arguments.status_file is not None:
        arguments.status_file.unlink(missing_ok=True)
    if arguments.cancel_file is not None:
        arguments.cancel_file.unlink(missing_ok=True)
    if arguments.diagnostics:
        emit = emitter(arguments.status_file)
        try:
            from .trt_backend import diagnostics
            emit({"event": "diagnostics", **diagnostics()})
            return 0
        except BaseException as error:
            emit({"event": "error", "message": str(error), "type": type(error).__name__})
            return 1
    if arguments.worker:
        if arguments.input is None or arguments.output is None:
            raise SystemExit("--worker requires --input and --output")
        return run_worker(arguments)
    from .gui import run_gui
    run_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
