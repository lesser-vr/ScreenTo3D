# cuda.bindings loads cuda.pathfinder dynamically, so keep this explicit import
# visible to PyInstaller's static analysis.
import cuda.pathfinder  # noqa: F401

from depthsbs_app.main import main


if __name__ == "__main__":
    raise SystemExit(main())
