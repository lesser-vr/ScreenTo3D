"""Check Qt PE import closure in an assembled Windows desktop (build-time only)."""
import argparse
import json
from pathlib import Path

def check(app):
    import pefile
    app=Path(app).resolve();qt=app/'packages/PySide6'
    files=[p for p in qt.rglob('*') if p.suffix.lower() in ('.dll','.pyd')]
    files.append(app/'out/qt-native-delivery/qt_native_delivery.dll')
    available={p.name.lower() for p in qt.iterdir() if p.is_file()}
    missing=[]
    for file in files:
        pe=pefile.PE(str(file),fast_load=True)
        try:
            pe.parse_data_directories(directories=[1,13])
            for directory in ('DIRECTORY_ENTRY_IMPORT','DIRECTORY_ENTRY_DELAY_IMPORT'):
                for entry in getattr(pe,directory,[]):
                    name=entry.dll.decode()
                    if name.lower().startswith('qt6') and name.lower() not in available:
                        missing.append(dict(binary=str(file.relative_to(app)),dependency=name))
        finally:pe.close()
    return dict(passed=not missing,checked_binaries=len(files),missing=missing,
        scope='Qt static and delay imports; dynamic Python/QML/plugin loading needs runtime checks')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app',type=Path);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();report=check(args.app)
    args.report.write_text(json.dumps(report,indent=2));print(json.dumps(report))
    raise SystemExit(0 if report['passed'] else 1)
