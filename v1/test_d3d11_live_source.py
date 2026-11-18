"""Exercise the real live pipeline with a privately owned D3D11 input window."""
import argparse
import json
import subprocess
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from unittest.mock import patch

import shiboken6
from PySide6.QtCore import QEventLoop, QSettings, QTimer, Qt
from PySide6.QtGui import QWindow

from screento3d_app.capture_mailbox import HEIGHT, WIDTH
from screento3d_app.desktop import create_app
from screento3d_app.desktop_preferences import DesktopPreferences
from screento3d_app.error_journal import record_error
from screento3d_app.live_sbs import RESET_GAP, RESET_RESIZE


def pump(seconds):
    loop = QEventLoop()
    timer = QTimer()
    timer.setTimerType(Qt.PreciseTimer)
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(round(seconds * 1000))
    loop.exec()


def wait_for(predicate, message, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        pump(.025)
    raise TimeoutError(message)


class InputWindow:
    def __init__(self, executable, log):
        self.process = subprocess.Popen(
            [str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=log, text=True, encoding='ascii', creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.messages = Queue()
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        try:
            for line in self.process.stdout:
                self.messages.put(line.split())
        finally:
            self.messages.put(['eof'])

    def receive(self, kind):
        def next_line():
            try:
                return self.messages.get_nowait()
            except Empty:
                return None

        reply = wait_for(next_line, f'D3D11 input window did not reply with {kind}')
        if reply[0] != kind:
            raise RuntimeError(f'Unexpected response from D3D11 input: {reply}')
        return list(map(int, reply[1:]))

    def send(self, command):
        self.process.stdin.write(command + '\n')
        self.process.stdin.flush()

    def command(self, command):
        self.send(command)
        presents, width, height, generation, gap_us = self.receive('ok')
        return dict(presents=presents, size=[width, height], generation=generation, gap_us=gap_us)

    def close(self):
        if self.process.poll() is None:
            try:
                self.send('close')
                self.process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait(timeout=5)
        self.reader.join(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()
        return self.process.returncode


def run(args, output):
    prefs = DesktopPreferences(QSettings(str(output / 'settings.ini'), QSettings.IniFormat))
    app, engine, desktop = create_app(prefs)
    live = desktop.live
    live.output_placement.path = output / 'placement.json'
    live.setMode('performance')
    live.setStereoLayout('half-tb')
    live.setPresentationHz(60)
    live.setCursor(False)
    failures = []
    live.errorOccurred.connect(lambda error: failures.append(error.error_id))
    report = dict(scope='Owned BGRA8 D3D11 source and real WGC/CUDA/Small/native output',
                  passed=False, cases=[], errors=failures)
    screens = app.screens()
    output_screen = next((i for i, screen in enumerate(screens) if screen is not app.primaryScreen()), 0)

    def journal(*args, **kwargs):
        with patch('screento3d_app.user_data.data_root', return_value=output):
            return record_error(*args, **kwargs)

    def require(predicate, label, seconds=15):
        def check():
            if failures:
                raise RuntimeError(f'{label}: {failures[-1]}')
            return predicate()
        return wait_for(check, label, seconds)

    def metrics():
        worker = live.diagnostic_worker.snapshot(include_failure=False)
        if worker is None:
            return None
        stats = live._stats()
        native = live.native.report()
        return dict(session=live.session, worker_pid=live.process.pid,
                    accepted=worker['accepted_frames'], output_size=[live.meta[WIDTH], live.meta[HEIGHT]],
                    submitted=native['output']['submitted_frames'],
                    pool_generation=getattr(live.native.pool, 'generation', None),
                    pools=native['live_pools'], nodes=native['live_nodes'],
                    resize_resets=stats[RESET_RESIZE], gap_resets=stats[RESET_GAP])

    def assert_recovered(previous, label, size=None, *, resized=False):
        def recovered():
            current = metrics() if live.active else None
            if not current or current['submitted'] < previous['submitted'] + 4:
                return None
            if size and current['output_size'] != size:
                return None
            if resized and not (current['resize_resets'] > previous['resize_resets']
                                and current['pool_generation'] > previous['pool_generation']):
                return None
            return current if current['pools'] == current['nodes'] == 1 else None

        current = require(recovered, label)
        if (current['session'], current['worker_pid']) != (previous['session'], previous['worker_pid']):
            raise RuntimeError(f'{label}: unexpected worker replacement')
        return current

    def start(source, hwnd, size):
        live.items = [dict(kind='window', id=hwnd, pid=source.process.pid,
                           label='Owned D3D11 source', width=size[0], height=size[1])]
        live.selected = 0
        live.start()
        live.showOutput(output_screen, False)
        desktop.main_window.hide()
        def ready():
            state = metrics() if live.active and live.native is not None and live.diagnostic_worker else None
            return state if state and state['submitted'] >= 12 and state['output_size'] == size else None

        try:
            require(ready, f'No native output for {size}', 25)
        except TimeoutError as error:
            raise TimeoutError(f'{error}. State: {metrics() if live.active else live.status}') from error
        if not (live.nativeEnabled and live.gpu_capture_selected):
            raise RuntimeError('Expected native output and GPU capture')

    def stopped():
        wait_for(lambda: not live.active, 'Worker did not stop', 20)
        counts = live.native.report()
        if counts['live_pools'] or counts['live_nodes'] or desktop.lease.owner:
            raise RuntimeError('Capture stopped with live delivery resources or lease')
        return [counts['live_pools'], counts['live_nodes']]

    def sample():
        return require(metrics, 'Capture counters unavailable')

    def append(**case):
        report['cases'].append(case)
        print(json.dumps(case), flush=True)

    source = None
    journal_patch = patch('screento3d_app.error_dialog.record_error', side_effect=journal)
    journal_patch.start()
    try:
        desktop.syncRuntimes()
        with (output / 'fixture.log').open('w', encoding='utf-8') as log:
            source = InputWindow(args.source, log)
            hwnd, = source.receive('ready')
            start(source, hwnd, [640, 360])
            for _ in range(args.repeat):
                for duration in (100, 250, 500):
                    previous = sample()
                    tick = time.monotonic()
                    fixture = source.command(f'hold {duration}')
                    held_ms = (time.monotonic() - tick) * 1000
                    assert fixture['gap_us'] >= duration*1000
                    after_hold = sample()
                    current = assert_recovered(after_hold, f'No recovery after {duration} ms hold')
                    assert current['accepted'] > after_hold['accepted']
                    assert current['gap_resets'] > previous['gap_resets'] or duration == 100
                    append(kind='hold', requested_ms=duration, command_ms=round(held_ms, 1),
                           present_gap_ms=fixture['gap_us']/1000, gap_reset_delta=current['gap_resets']-previous['gap_resets'])
            sizes = ([1280, 720], [1920, 1080], [640, 360])
            for _ in range(args.repeat):
                for size in sizes:
                    previous = sample()
                    fixture = source.command(f'resize {size[0]} {size[1]}')
                    assert fixture['size'] == size
                    current = assert_recovered(previous, 'No output after input resize', size, resized=True)
                    append(kind='resize', input_size=size, fixture_generation=fixture['generation'],
                           pool_generation=current['pool_generation'], resize_resets=current['resize_resets'])
                previous = sample()
                old = source.command('status')
                fixture = source.command('resize 640 360')
                assert fixture['generation'] == old['generation'] + 1
                current = assert_recovered(previous, 'No output after same-size buffer rebuild', [640, 360])
                append(kind='same_size_rebuild', fixture_generation=fixture['generation'],
                       pool_generation=current['pool_generation'])
            for _ in range(args.repeat):
                for expected in (QWindow.FullScreen, QWindow.Windowed):
                    previous = sample()
                    live.toggleOutputFullscreen()
                    require(lambda: live.output_window.visibility() == expected, 'Output did not switch mode')
                    assert_recovered(previous, 'No output after window mode switch', [640, 360])
                    append(kind='output_mode', fullscreen=expected == QWindow.FullScreen)
            for _ in range(args.repeat):
                live.stop()
                append(kind='stop_restart', resources_after_stop=stopped())
                start(source, hwnd, [640, 360])
            # A close can be noticed by the GUI validator or the worker.
            source.send('close')
            wait_for(lambda:bool(failures), 'Missing source close error')
            assert failures == ['E_CAPTURE_SOURCE_CLOSED'], failures
            append(kind='source_close', error=failures.pop(), resources_after_stop=stopped())
            assert source.close() == 0
            source = InputWindow(args.source, log)
            hwnd, = source.receive('ready')
            start(source, hwnd, [640, 360])
            live.process.terminate()
            wait_for(lambda:bool(failures), 'Missing worker exit error')
            assert failures == ['E_CAPTURE_STOPPED'], failures
            append(kind='worker_exit', error=failures.pop(), resources_after_stop=stopped())
            start(source, hwnd, [640, 360])
            live.stop()
            stopped()
            records = [json.loads(line) for line in (output/'logs/errors.jsonl').read_text(encoding='utf-8').splitlines()]
            assert [record['error_id'] for record in records] == ['E_CAPTURE_SOURCE_CLOSED', 'E_CAPTURE_STOPPED']
            events = records[-1]['diagnostics']['events']
            assert any(event['name'] == 'worker_exit' and event['data']['exit_code'] is not None for event in events)
            assert all(record['diagnostics']['samples'] for record in records)
            report['fixture_exit'] = source.close()
            source = None
            assert report['fixture_exit'] == 0
            report['expected_errors_logged'] = len(records)
            report['passed'] = True
    except Exception as error:
        report['failure'] = str(error)
        raise
    finally:
        try:
            if live.active:
                live.stop()
                stopped()
        finally:
            try:
                if source is not None:
                    report['fixture_exit'] = source.close()
                desktop.error_dialog.close()
                desktop.main_window.close()
                app.processEvents()
                shiboken6.delete(engine)
            finally:
                journal_patch.stop()
                (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('out/d3d11-live-source/d3d11-live-source.exe'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--repeat', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 20:
        parser.error('--repeat must be between 1 and 20')
    args.source = args.source.resolve(strict=True)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    run(args, args.output)


if __name__ == '__main__':
    main()
