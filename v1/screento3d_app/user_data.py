"""User-data namespace and lossless, non-overwriting legacy migration."""
from contextlib import contextmanager
import os
from pathlib import Path
import time

from .messages import ErrorMessage as E
from .environment import get as app_env

DATA_DIRECTORY='ScreenTo3D'
LEGACY_DIRECTORIES=('StereoTo3D','DepthSBS')


def data_root():
    """Path discovery is pure: inventory/tests must not migrate user data."""
    base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))
    return base/DATA_DIRECTORY


def _check(path,root):
    if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
        raise OSError('Linked app data is not migrated')
    if not path.resolve().is_relative_to(root.resolve()):
        raise OSError('App data path escapes its root')


@contextmanager
def _migration_lock(root):
    _check(root/'.migration.lock',root)
    with (root/'.migration.lock').open('a+b') as stream:
        if stream.seek(0,2)==0:stream.write(b'0');stream.flush()
        deadline=time.monotonic()+30
        while True:
            stream.seek(0)
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()>=deadline:raise TimeoutError('App data migration is busy') from None
                time.sleep(.05)
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream,fcntl.LOCK_UN)


def _merge_missing(source,target,legacy,root,*,keep_logs=False):
    _check(source,legacy);_check(target,root)
    if keep_logs and source==legacy/'logs':return
    if not target.exists():
        try:source.rename(target);return
        except (FileExistsError,FileNotFoundError):
            if not source.exists() and target.exists():return
            if not target.exists():raise
    if source.is_dir() and target.is_dir():
        for child in source.iterdir():_merge_missing(child,target/child.name,legacy,root,keep_logs=keep_logs)
        try:source.rmdir()  # Only empty legacy folders; conflicts are retained.
        except OSError:pass
    elif source.is_dir()!=target.is_dir():
        raise OSError('Conflicting app data types')
    # An existing file always wins; preserve the conflicting legacy file too.


def _adopt_legacy(requested,name):
    legacy=requested.with_name(name)
    _check(requested,requested.parent);_check(legacy,requested.parent)
    if not legacy.exists():return
    # Store Python overlays a private LocalCache on normal LocalAppData.
    # Operate on physical siblings, never move backing production data into
    # a redirected development root or rename an overlaid directory view.
    legacy=legacy.resolve()
    root=requested.resolve() if requested.exists() else legacy.with_name(DATA_DIRECTORY)
    if legacy.parent!=root.parent:return
    if not legacy.is_dir() or (root.exists() and not root.is_dir()):
        raise OSError('Invalid app data directory')
    # Older launchers own an open log here. Keep that directory until a later
    # current-name launch, while adopting required models and caches now.
    active_log=app_env('SCREENTO3D_LAUNCH_LOG')
    keep_logs=bool(active_log and Path(active_log).resolve().is_relative_to(legacy/'logs'))
    if keep_logs:root.mkdir(exist_ok=True)
    if not root.exists():
        try:legacy.rename(root);return
        except (FileExistsError,FileNotFoundError):
            if not legacy.exists() and root.is_dir():return
            if not root.is_dir():raise
    with _migration_lock(root):
        if legacy.exists():_merge_missing(legacy,root,legacy,root,keep_logs=keep_logs)


def migrate_legacy_data():
    """Adopt the interim typo first, then older data; never override current data."""
    requested=data_root()
    try:
        for name in LEGACY_DIRECTORIES:_adopt_legacy(requested,name)
        return requested
    except OSError:
        # Do not leak private paths or turn migration failure into a fresh install.
        raise OSError(E('E_DATA_MIGRATION')) from None
