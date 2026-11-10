"""Validate Qt catalogs against Python/QML sources and compile bundled translations."""
import argparse
import ast
import json
from pathlib import Path
import re
from string import Formatter
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'v1/depthsbs_app'


def sources():
    result=set()
    for path in APP.glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if (isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('M','Message')
                    and node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str)):
                result.add(('ScreenTo3D',node.args[0].value))
    for path in (APP/'qml').glob('*.qml'):
        for match in re.finditer(r'\bqsTr\(("(?:[^"\\]|\\.)*")\)',path.read_text(encoding='utf-8')):
            result.add((path.stem,json.loads(match[1])))
    return result


def placeholders(text):
    return sorted((name,spec,conversion) for _,name,spec,conversion in Formatter().parse(text) if name is not None)


def validate(path):
    tree=ET.parse(path)
    catalog={}
    for context in tree.getroot().findall('context'):
        name=context.findtext('name')
        for message in context.findall('message'):
            source=message.findtext('source') or ''
            translation=message.find('translation')
            text='' if translation is None else ''.join(translation.itertext())
            if translation is None or translation.get('type')=='unfinished' or not text:
                raise ValueError(f'Unfinished translation: {name}: {source}')
            if placeholders(source)!=placeholders(text):
                raise ValueError(f'Translation placeholders differ: {name}: {source}')
            if (name,source) in catalog:
                raise ValueError(f'Duplicate translation: {name}: {source}')
            catalog[name,source]=text
    missing=sources()-set(catalog)
    if missing:
        raise ValueError('Missing translations:\n'+'\n'.join(f'{context}: {source}' for context,source in sorted(missing)))
    return len(catalog)


def build(*,check=False):
    path=APP/'translations/screento3d_ko.ts'
    count=validate(path)
    if not check:
        tool=ROOT/'out/gui-python-deps/PySide6/lrelease.exe'
        if not tool.is_file():
            import PySide6
            tool=Path(PySide6.__file__).parent/'lrelease.exe'
        if not tool.is_file():
            raise FileNotFoundError('PySide6 lrelease.exe is required to build the Qt catalog')
        subprocess.run([str(tool),str(path),'-qm',str(path.with_suffix('.qm'))],check=True)
    print(f'Validated {count} Korean translations against current English sources.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    build(check=parser.parse_args().check)
