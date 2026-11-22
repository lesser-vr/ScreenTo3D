"""Extract a shareable report from one local error record."""
from datetime import datetime
import re
from string import Formatter

from .catalogs import ERRORS
from .messages import ErrorMessage, Message as M

ACTIVITIES = {
    'live': M('Live 3D'),
    'model': M('Model installation'),
    'file': M('File conversion'),
    'app': M('Application'),
}
SETTINGS = {
    'model': {'da2-small', 'da2-base', 'vda-small', 'ovda-small-c16'},
    'layout': {'full-sbs', 'half-sbs', 'full-tb', 'half-tb'},
    'mode': {'performance', 'balanced', 'video-quality'},
}
EVENTS = {
    'start_requested', 'output_requested', 'output_geometry', 'fullscreen_requested',
    'vfg_requested', 'displays_changed', 'stop_requested', 'worker_exit', 'abort',
    'before_abort_cleanup', 'before_worker_cleanup', 'start_failed',
    'reported_exception', 'reported_error',
}


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _number(value, minimum=0, maximum=2**63-1):
    return value if type(value) is int and minimum <= value <= maximum else None


def _dimensions(value):
    if isinstance(value, (list, tuple)) and len(value) == 2 and all(
        _number(side, 1, 32768) is not None for side in value
    ):
        return f'{value[0]}×{value[1]}'
    return None


def _items(value, limit):
    return value[-limit:] if isinstance(value, list) else []


def _matched(value, pattern):
    return value if isinstance(value, str) and re.fullmatch(pattern, value) else None


def _relative_ms(time, end):
    time = _number(time)
    if end is None or time is None or not 0 <= end-time <= 60_000_000_000:
        return None
    return (time-end)//1_000_000


def prepare_report(record):
    """Project allowlisted values. Raw logs, paths and exception text stay local."""
    if not isinstance(record, dict) or record.get('schema') != 1:
        return None
    timestamp = record.get('timestamp')
    if not isinstance(timestamp, str) or len(timestamp) > 48:
        return None
    try:
        occurred = datetime.fromisoformat(timestamp)
        if occurred.utcoffset() is None:
            return None
    except ValueError:
        return None
    error_id = _matched(record.get('error_id'), r'E_[A-Z0-9_]{1,80}')
    if not error_id:
        return None

    diagnostics = _mapping(record.get('diagnostics'))
    context = _mapping(diagnostics.get('context'))
    settings = _mapping(context.get('settings'))
    identity = _mapping(context.get('identity'))
    build = _mapping(identity.get('build'))
    activity = record.get('activity')
    if not isinstance(activity, str) or activity not in ACTIVITIES:
        if error_id.startswith(('E_CAPTURE_', 'E_LIVE_', 'E_MONITOR_', 'E_VFG_')) or diagnostics:
            activity = 'live'
        elif error_id.startswith(('E_MODEL_', 'E_ENGINE_', 'E_DOWNLOAD_', 'E_RUNTIME_')):
            activity = 'model'
        elif error_id.startswith(('E_FILE_', 'E_CONVERSION', 'E_WORKER_')):
            activity = 'file'
        else:
            activity = 'app'

    report = dict(
        time=occurred, error_id=error_id, activity=activity,
        version=_matched(record.get('app_version'), r'[0-9][0-9A-Za-z.+-]{0,31}'),
        build=_matched(build.get('source_commit'), r'[0-9a-fA-F]{7,64}'),
        profile={},
        samples=[], events=[],
    )
    if not report['build']:
        report['build'] = _matched(identity.get('live_source_sha256'), r'[0-9a-fA-F]{64}')
    for key, allowed in SETTINGS.items():
        value = settings.get(key)
        if isinstance(value, str) and value in allowed:
            report['profile'][key] = value
    if _number(settings.get('limit_hz'), 0, 300) is not None:
        report['profile']['limit_hz'] = settings['limit_hz']
    if type(settings.get('vfg')) is bool:
        report['profile']['vfg'] = settings['vfg']

    end = _number(diagnostics.get('qpc_ns'))
    for event in _items(diagnostics.get('events'), 64):
        event = _mapping(event)
        name = event.get('name')
        if not isinstance(name, str) or name not in EVENTS:
            continue
        data = _mapping(event.get('data'))
        exit_code = _number(data.get('exit_code'), -2**31, 2**32-1)
        if name == 'worker_exit' and exit_code is not None:
            report['exit_code'] = exit_code
        offset = _relative_ms(event.get('qpc_ns'), end)
        if offset is not None:
            safe_event = dict(ms=offset, name=name)
            for key in ('fullscreen', 'was_fullscreen', 'enabled'):
                if type(data.get(key)) is bool:
                    safe_event[key] = data[key]
            if name == 'displays_changed' and isinstance(data.get('screens'), list):
                safe_event['screen_count'] = min(len(data['screens']), 64)
            report['events'].append(safe_event)

    for sample in _items(diagnostics.get('samples'), 61):
        sample = _mapping(sample)
        offset = _relative_ms(sample.get('qpc_ns'), end)
        if offset is None:
            continue
        state = _mapping(sample.get('state'))
        capture = _mapping(state.get('capture'))
        accepted = _mapping(state.get('accepted_capture'))
        source = _mapping(state.get('source'))
        output = _mapping(state.get('output'))
        safe_sample = dict(
            ms=offset,
            input_px=_dimensions(source.get('client_px')) or _dimensions(source.get('selected_px'))
            or _dimensions([accepted.get('width'), accepted.get('height')]),
            output_px=_dimensions(output.get('buffer_px')),
            received=_number(capture.get('received')),
            processed=_number(_mapping(state.get('processing')).get('frames')),
            submitted=_number(output.get('submitted')),
            resizes=_number(accepted.get('resizes')),
            max_input_gap_ms=gap//1_000_000 if (gap := _number(accepted.get('max_source_gap_ns'))) is not None else None,
            gpu_pct=_number(_mapping(state.get('gpu')).get('percent'), 0, 100),
        )
        for key in ('visible', 'minimized'):
            if type(source.get(key)) is bool:
                safe_sample[f'input_{key}'] = source[key]
        if type(output.get('fullscreen')) is bool:
            safe_sample['fullscreen'] = output['fullscreen']
        report['samples'].append({key: value for key, value in safe_sample.items() if value is not None})
    return report


def report_text(report, translate, *, note='', include_diagnostics=False, pc_info=None):
    error_id = report['error_id']
    lines = [
        translate(M('ScreenTo3D error report')),
        translate(M('Error ID')) + ': ' + error_id,
        translate(M('Time')) + ': ' + report['time'].isoformat(sep=' ', timespec='milliseconds'),
        translate(M('Activity')) + ': ' + translate(ACTIVITIES[report['activity']]),
    ]
    if report['version']:
        lines.append(translate(M('App version')) + ': ' + report['version'])
    if report['build']:
        lines.append(translate(M('Build')) + ': ' + report['build'])
    # Use the trusted catalog only. Parameterized entries may require opaque
    # local values, so the stable ID is the summary for those entries.
    definition = ERRORS.get(error_id, ERRORS['E_UNKNOWN'])
    if not any(field is not None for _, field, _, _ in Formatter().parse(definition['public'])):
        lines.append(translate(ErrorMessage(error_id, public=True)))
    for key, label in (
        ('model', M('Depth model')), ('mode', M('Processing mode')),
        ('layout', M('Stereo format')), ('limit_hz', M('FPS limit')), ('vfg', M('VFG')),
    ):
        if key in report['profile']:
            value = report['profile'][key]
            if type(value) is bool:
                value = translate(M('On') if value else M('Off'))
            elif key == 'limit_hz' and value == 0:
                value = translate(M('Unlimited'))
            lines.append(f'{translate(label)}: {value}')
    if 'exit_code' in report:
        lines.append(f"{translate(M('Worker exit code'))}: {report['exit_code']}")
    if pc_info is not None:
        lines.extend(('', translate(M('PC information at report preparation'))))
        for key, label in (('windows', M('Windows version')), ('cpu', M('Processor'))):
            if key in pc_info:
                lines.append(f'{translate(label)}: {pc_info[key]}')
        if 'memory_gib' in pc_info:
            lines.append(f"{translate(M('Physical memory'))}: {pc_info['memory_gib']:.1f} GiB")
        for name, driver in pc_info.get('gpu', ()):
            lines.append(f"{translate(M('Graphics adapter'))}: {name}")
            if driver:
                lines.append(f"  {translate(M('Graphics driver'))}: {driver}")
        if not pc_info or 'gpu' not in pc_info:
            lines.append(translate(M('Graphics adapter details are unavailable.')))
    if note.strip():
        lines.extend(('', translate(M('What happened just before the error?')), note.strip()[:500]))
    if include_diagnostics and (report['samples'] or report['events']):
        lines.extend(('', translate(M('Last 60 seconds of diagnostics')), translate(M('Times are relative to the error, in milliseconds.'))))
        for entry in sorted(report['samples'] + report['events'], key=lambda row: row['ms']):
            offset = entry['ms']
            details = ' · '.join(f'{k}={v}' for k, v in entry.items() if k != 'ms')
            lines.append(f'{offset:>6} ms  {details}')
    return '\n'.join(lines) + '\n'
