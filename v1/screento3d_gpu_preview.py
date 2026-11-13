"""Separate, opt-in entry point; never selected by the CPU release."""
import cuda.pathfinder  # noqa: F401

from screento3d_app.main import main

if __name__ == '__main__':
    raise SystemExit(main(gpu_preview=True))
