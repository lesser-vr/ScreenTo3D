import os
import sys
from pathlib import Path

_media_tools = None
_resource_root = None


def configure_resource_root(directory):
    """Explicit source-desktop resource location; never inferred from cwd."""
    global _resource_root
    directory = Path(directory).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError('Resource root must be a directory')
    _resource_root = directory


def configure_media_tools(directory):
    global _media_tools
    directory = Path(directory).resolve(strict=True)
    if not all((directory / f'{name}.exe').is_file() for name in ('ffmpeg', 'ffprobe')):
        raise ValueError('Media tools directory must contain ffmpeg.exe and ffprobe.exe')
    _media_tools = directory


def bundle_root() -> Path:
    if _resource_root is not None:
        return _resource_root
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def executable_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return bundle_root()


def resource_path(relative: str) -> Path:
    if _media_tools is not None and relative in ('ffmpeg/ffmpeg.exe', 'ffmpeg/ffprobe.exe'):
        return _media_tools / Path(relative).name
    candidates = [bundle_root() / relative, executable_root() / relative]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def cache_root() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    path = base / "DepthSBS" / "engines"
    path.mkdir(parents=True, exist_ok=True)
    return path


def prepare_dll_search_path(directory=None):
    runtime = resource_path("runtime") if directory is None else Path(directory).resolve(strict=True)
    if directory is not None and not runtime.is_dir():
        raise NotADirectoryError(runtime)
    if runtime.is_dir():
        # TensorRT's Windows Python loader explicitly enumerates PATH.
        path = os.environ.get("PATH", "")
        if path.split(os.pathsep, 1)[0] != str(runtime):
            os.environ["PATH"] = str(runtime) + os.pathsep + path
        return os.add_dll_directory(str(runtime))
