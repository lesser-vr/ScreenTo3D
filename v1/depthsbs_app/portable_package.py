"""Conservative file pruning for the ordinary desktop runtime, not source research."""
from pathlib import PurePosixPath
from pathlib import Path
import ast
import json

DEVELOPMENT_SUFFIXES={'.lib','.a','.exp','.h','.hpp','.cuh','.pdb','.obj','.o','.cmake',
                      '.c','.cc','.cpp','.cxx','.cu','.pyx','.pxd','.pxi'}
QT_PROFILE=json.loads(Path(__file__).with_name('qt_portable_profile.json').read_text(encoding='utf-8'))
if QT_PROFILE['schema']!=1:raise ValueError('Invalid bundled Qt deployment profile')
QT_BINDINGS={name.lower() for name in QT_PROFILE['bindings']}
QT_LIBRARIES={name.lower() for name in QT_PROFILE['libraries']}
QT_QML_EXCLUDED=set(QT_PROFILE['excluded_qml_modules'])
UNUSED_TENSORRT={'nvinfer_lean_11.dll','nvinfer_dispatch_11.dll','nvinfer_vc_plugin_11.dll'}


def runtime_exclusion(name):
    return 'unused-tensorrt' if str(name).lower() in UNUSED_TENSORRT else ''


def validate_qt_source(directory):
    directory=Path(directory)
    tree=ast.parse((directory/'__init__.py').read_text(encoding='utf-8'))
    version=next((ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Name) and target.id=='__version__' for target in node.targets)),None)
    if version!=QT_PROFILE['pyside_version']:raise ValueError('Qt deployment profile requires PySide6 '+QT_PROFILE['pyside_version'])
    for name in [*(name+'.pyd' for name in QT_PROFILE['bindings']),*QT_PROFILE['libraries']]:
        if not (directory/name).is_file():raise ValueError('Qt deployment input is incomplete: '+name)


def exclusion(relative,*,is_dir=False):
    path=PurePosixPath(str(relative).replace('\\','/'))
    name=path.name.lower()
    # License texts such as COPYING.LIB must survive extension-based pruning.
    if name.startswith(('license','licence','copying','notice','copyright')) or 'licenses' in (p.lower() for p in path.parts):
        return ''
    if '__pycache__' in path.parts or name.endswith('.pyc'):
        return 'bytecode'
    if is_dir:
        return ''  # Traverse so nested license files cannot be skipped with a parent.
    if path.suffix.lower() in DEVELOPMENT_SUFFIXES or name.endswith('.h.in'):
        return 'development'
    lower=path.as_posix().lower()
    if lower=='packages/torch/include' or lower.startswith('packages/torch/include/'):
        return 'development'
    if lower.startswith('packages/pyside6/') and any(
            part.startswith(('qt6webengine','qtwebengine')) or 'webengine' in part
            for part in (p.lower() for p in path.parts[2:])):
        return 'unused-webengine'
    if lower.startswith('packages/pyside6/'):
        parts=path.parts[2:]
        if parts[0] in QT_PROFILE['unused_directories']:return 'unused-qt'
        if len(parts)==1:
            if name.startswith('qt6') and name.endswith('.dll') and name not in QT_LIBRARIES:return 'unused-qt'
            if name.startswith('qt') and path.suffix.lower() in ('.pyd','.pyi') and path.stem.lower() not in QT_BINDINGS:return 'unused-qt'
            if name.endswith('.exe') or name.startswith(('avcodec-','avformat-','avutil-','swresample-','swscale-')):return 'unused-qt'
        if parts[0]=='plugins' and len(parts)>1 and parts[1] not in QT_PROFILE['plugin_families']:return 'unused-qt'
        if parts[0]=='qml' and any('/'.join(parts[1:n]) in QT_QML_EXCLUDED for n in range(2,len(parts))):return 'unused-qt'
    return ''
