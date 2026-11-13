"""Bounded handoff from an authenticated browser to the pinned pack installer."""
from pathlib import Path
from urllib.parse import quote

RELEASE = 'https://github.com/lesser-vr/ScreenTo3D/releases/download/v1.0.0/'


def release_url(filename):
    if Path(filename).name != filename or '/' in filename or '\\' in filename:
        raise ValueError('Expected a release asset filename')
    return RELEASE + quote(filename, safe='')


class DownloadHandoff:
    """Observe only named completed files; never read browser credentials/history."""
    def __init__(self, directory, filename, size, now):
        self.directory = Path(directory)
        name = Path(filename)
        self.names = [filename] + [f'{name.stem} ({i}){name.suffix}' for i in range(1, 21)]
        self.size = size
        self.deadline = now + 15 * 60
        self.previous = {}

    def ready(self, now):
        if now >= self.deadline:
            raise TimeoutError
        current = {}
        for name in self.names:
            path = self.directory / name
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                stat = path.stat()
                if stat.st_size != self.size:
                    continue
                identity = (stat.st_size, stat.st_mtime_ns)
                current[path] = identity
                if self.previous.get(path) == identity:
                    return path
            except OSError:
                continue  # Browser can rename/remove a file during the observation.
        self.previous = current
        return None
