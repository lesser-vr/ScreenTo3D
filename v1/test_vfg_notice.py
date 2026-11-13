"""Rendered VFG feedback: eye placement, Half decoding and bounded animation."""
import argparse
import json
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QPointF
from screento3d_app.desktop import create_app
from screento3d_app.stereo_layout import dimensions
import shiboken6


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with patch('screento3d_app.live_preview.windows', return_value=[]):
        app, engine, desktop = create_app()
    live = desktop.live
    live.output_placement.save = lambda: None
    output = live.output_window
    output.resize(960, 540)
    output.showNormal()
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
    notice = desktop.main_window.findChild(QObject, 'vfgNotice')
    results = dict(layouts=[], warnings=warnings)

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(.003)

    def capture(name):
        assert output.grabWindow().save(str(args.output / (name + '.png')))

    try:
        for layout in ('full-sbs', 'half-sbs', 'full-tb', 'half-tb'):
            live.setStereoLayout(layout)
            live.meta[2:4] = dimensions(960, 540, layout)
            live.changed.emit()
            live.vfgNotification.emit('VFG 준비 중…', True)
            pump(.15)
            labels = []
            todo = list(notice.childItems())
            while todo:
                item = todo.pop()
                if item.objectName() == 'vfgNoticeLabel':
                    labels.append(item)
                todo.extend(item.childItems())
            assert len(labels) == 2
            rect = notice.mapToScene(QPointF(0, 0))
            centers = []
            for label in labels:
                assert label.property('font').pixelSize() == 14
                center = label.mapToScene(QPointF(label.width() / 2, label.height() / 2))
                centers.append((center.x() - rect.x(), center.y() - rect.y()))
                start = label.mapToScene(QPointF(0, 0))
                end = label.mapToScene(QPointF(14, 14))
                x = (end.x() - start.x()) * (2 if layout == 'half-sbs' else 1)
                y = (end.y() - start.y()) * (2 if layout == 'half-tb' else 1)
                assert abs(x-y) < .01, (layout, x, y)
                assert label.property('contentWidth') <= label.width()
            expected = ([(notice.width()/2, notice.height()/4), (notice.width()/2, notice.height()*3/4)]
                        if layout.endswith('tb') else
                        [(notice.width()/4, notice.height()/2), (notice.width()*3/4, notice.height()/2)])
            for actual, wanted in zip(sorted(centers), sorted(expected)):
                # QML center anchors snap to pixels before Half-axis scaling.
                assert all(abs(a-b) <= 1 for a, b in zip(actual, wanted)), (actual, wanted)
            capture(layout + '-preparing')
            results['layouts'].append(dict(layout=layout, centers=centers, balanced_after_decode=True))

        # Preparation must survive the completion message's normal timeout.
        pump(1.8)
        assert notice.property('pending') and notice.opacity() == 1
        for text in ('VFG ON', 'VFG OFF'):
            live.vfgNotification.emit(text, False)
            pump(.05)
            capture(text.replace(' ', '-').lower())
            pump(1.3)
            assert notice.property('message') == text and notice.opacity() == 1
            pump(.25)
            assert 0 < notice.opacity() < 1, notice.opacity()
            capture(text.replace(' ', '-').lower() + '-fading')
            pump(.3)
            assert notice.opacity() == 0 and notice.property('message') == ''

        # A second transition interrupts the old fade without a stale timer.
        live.vfgNotification.emit('VFG ON', False)
        pump(1.6)
        live.vfgNotification.emit('VFG 끄는 중…', True)
        pump(1.8)
        assert notice.opacity() == 1 and notice.property('pending')
        live.vfgNotification.emit('', False)
        pump(.1)
        assert notice.opacity() == 0
        live.vfgNotification.emit('VFG OFF', False)
        output.hide()
        pump(.1)
        assert notice.opacity() == 0 and notice.property('message') == ''
        assert not warnings, warnings
        results.update(passed=True, hold_ms=1500, fade_ms=250, cancel_and_hide_clear=True,
                       interruption=True, captured_input=False)
    finally:
        (args.output/'report.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        shiboken6.delete(engine)


if __name__ == '__main__':
    main()
