"""Bounded, app-local history of errors reported to the native error window."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
from threading import Lock

from . import __version__
from .messages import as_error, payload

MAX_LOG_BYTES = 1024 * 1024
MAX_RECORD_BYTES = 128 * 1024
_lock = Lock()


def make_error_record(error, *, title, message, displayed_text, diagnostics=None, activity=None):
    original = dict(schema=1, timestamp=datetime.now(timezone.utc).astimezone().isoformat(timespec='milliseconds'),
                    pid=os.getpid(), app_version=__version__, error_id=error.error_id,
                    title=str(title), message=str(message), details=error.details,
                    displayed_text=str(displayed_text), error=payload(error),
                    launch_log=Path(os.environ.get('SCREENTO3D_LAUNCH_LOG', '')).name)
    if diagnostics is not None:
        original['diagnostics'] = diagnostics
    if activity is not None:
        original['activity'] = activity
    return original


def _encoded_record(original):
    for limit in (8192, 4096, 1024, 256, 64):
        truncated = [False]
        def bounded(value, depth=0):
            if depth > 10:
                truncated[0] = True
                return '[nesting limit]'
            if isinstance(value, str):
                if len(value) > limit:
                    truncated[0] = True
                    return value[:limit] + ' [truncated]'
                return value
            if isinstance(value, dict):
                if len(value) > 64:truncated[0] = True
                return {str(k): v if k == 'error_id' else bounded(v, depth + 1) for k, v in list(value.items())[:64]}
            if isinstance(value, (list, tuple)):
                if len(value) > 64:truncated[0] = True
                return [bounded(v, depth + 1) for v in value[:64]]
            if isinstance(value, float) and not math.isfinite(value):return str(value)
            return value
        record = bounded(original)
        record['truncated'] = truncated[0]
        encoded = (json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8', 'backslashreplace')
        if len(encoded) <= MAX_RECORD_BYTES:return encoded
    # Keep a valid, identified record even for an unusually broad nested error.
    record = {k: original[k] for k in ('schema', 'timestamp', 'pid', 'app_version', 'error_id')}
    record.update(message=original['message'][:256], details=original['details'][:256], truncated=True)
    return (json.dumps(record, ensure_ascii=False) + '\n').encode('utf-8', 'backslashreplace')


def record_error(error, *, title=None, message=None, displayed_text=None, diagnostics=None, entry=None):
    """Record one report, never raise into error handling; no files on import."""
    try:
        from .user_data import data_root, _check
        error = as_error(error)
        if entry is None:
            entry = make_error_record(error, title=title, message=message,
                                      displayed_text=displayed_text, diagnostics=diagnostics)
        encoded = _encoded_record(entry)
        root = data_root()
        directory = root / 'logs'
        current = directory / 'errors.jsonl'
        previous = directory / 'errors.1.jsonl'
        with _lock:
            # Never follow a redirected log path outside the portable data root.
            for path in (directory, current, previous):_check(path, root)
            directory.mkdir(parents=True, exist_ok=True)
            if current.exists() and current.stat().st_size + len(encoded) > MAX_LOG_BYTES:
                current.replace(previous)
            with current.open('ab') as stream:
                if stream.write(encoded) != len(encoded):raise OSError('Incomplete error journal write')
        return True
    except Exception as failure:
        # A full disk or unavailable log directory must not hide the real error.
        try:
            if sys.stderr is not None:
                sys.stderr.write(f'ScreenTo3D error history unavailable ({type(failure).__name__}); error ID: {getattr(error, "error_id", "E_UNKNOWN")}\n')
                sys.stderr.flush()
        except Exception:
            pass
        return False


def read_recent_reports(limit=50):
    """Read only the rotated local journal and return sanitized entries."""
    from .error_report import prepare_report
    from .user_data import data_root, _check

    root = data_root()
    directory = root / 'logs'
    reports = []
    partial = False
    with _lock:
        for filename in ('errors.1.jsonl', 'errors.jsonl'):
            path = directory / filename
            try:
                _check(path, root)
                with path.open('rb') as stream:
                    content = stream.read(MAX_LOG_BYTES + 1)
            except FileNotFoundError:
                continue
            except OSError:
                partial = True
                continue
            if len(content) > MAX_LOG_BYTES:
                partial = True
                content = content[:MAX_LOG_BYTES]
            for line in content.splitlines():
                if len(line) > MAX_RECORD_BYTES:
                    partial = True
                    continue
                try:
                    report = prepare_report(json.loads(line))
                except (ValueError, RecursionError):
                    report = None
                if report is None:
                    partial = True
                else:
                    reports.append(report)
    reports.sort(key=lambda report: report['time'])
    return list(reversed(reports[-limit:])), partial
