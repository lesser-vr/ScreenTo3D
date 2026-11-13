"""Source desktop worker bootstrap; uses unchanged validated conversion stages."""

import json
import os
import sys

from .desktop_jobs import BUNDLE
from . import resources


def main():
    # Explicit trusted local resource installation, not cwd/DLL discovery.
    resources.configure_resource_root(BUNDLE)
    from .main import build_parser, run_worker

    args = build_parser().parse_args()
    handles = []
    if args.runtime_dir is not None:
        from .desktop_runtimes import resolve
        args.runtime_dir=resolve(args.runtime_dir,'trt-core')
        handles.append(os.add_dll_directory(str(args.runtime_dir.resolve(strict=True))))
    from .desktop_runtimes import resolve
    args.media_tools=resolve(args.media_tools,'media-tools')
    resources.configure_media_tools(args.media_tools)
    # Parent creates a unique absent cancel marker. Do NOT unlink it at startup:
    # a close/cancel immediately after process launch must not be lost.
    print(json.dumps({"event": "worker_ready"}), flush=True)
    try:
        return run_worker(args)
    finally:
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    sys.exit(main())
