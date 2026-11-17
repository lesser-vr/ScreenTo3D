"""Portable, process-local UI typeface shared by QML and native error widgets."""
from pathlib import Path
import hashlib
import json
import sys

FAMILY = 'Pretendard Variable'
FONT_FILENAME = 'PretendardVariable.ttf'
DIRECTORY = Path(__file__).with_name('assets') / 'fonts'


def validate_assets(directory=None):
    """Release builds require the complete pinned font and its upstream notice."""
    directory = Path(directory) if directory is not None else DIRECTORY
    manifest = json.loads((directory / 'font-manifest.json').read_text(encoding='utf-8'))
    if manifest['family'] != FAMILY or set(manifest['files']) != {FONT_FILENAME, 'OFL.txt'}:
        raise ValueError('Invalid UI font manifest')
    for name, expected in manifest['files'].items():
        data = (directory / name).read_bytes()
        if len(data) != expected['bytes'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
            raise ValueError('Bundled UI font asset differs from its pin: ' + name)
    return manifest


def install(app):
    """Load once before any windows; never install an OS font or use the network.

    A damaged cosmetic asset must not prevent access to the application. The
    release validator catches it; runtime leaves the system family usable.
    """
    from PySide6.QtGui import QFont, QFontDatabase

    identifier = getattr(app, '_screento3d_font_id', None)
    if identifier is None:
        identifier = QFontDatabase.addApplicationFont(str(DIRECTORY / FONT_FILENAME))
        app._screento3d_font_id = identifier
        if identifier < 0:
            print('Bundled UI font unavailable; using the system font.', file=sys.stderr)
    font = QFont(app.font())
    if identifier >= 0 and FAMILY in QFontDatabase.applicationFontFamilies(identifier):
        font.setFamily(FAMILY)
    font.setPixelSize(14)
    font.setWeight(QFont.Normal)
    app.setFont(font)
    return font.family()
