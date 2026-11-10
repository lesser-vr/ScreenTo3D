"""Trusted, bundled language/error definitions. Safe to import in isolated workers."""
import json
from pathlib import Path
import re
from string import Formatter

DIRECTORY = Path(__file__).with_name('translations')


def load_languages(path=None):
    data = json.loads((path or DIRECTORY / 'languages.json').read_text(encoding='utf-8'))
    languages = {}
    for item in data['languages']:
        code = item['code']
        if len(code)>63 or not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', code) or code in languages:
            raise ValueError('Invalid or duplicate language code')
        if not re.fullmatch(r'[a-zA-Z]{2,3}(?:-[A-Za-z0-9]{2,8})*', item['locale']):
            raise ValueError('Invalid language locale')
        for name in [item['catalog'], *item.get('qt_catalogs', [])]:
            if name is not None and not re.fullmatch(r'[A-Za-z0-9_-]+', name):
                raise ValueError('Catalog names must be bundled basenames')
        if not isinstance(item['name'], str) or not item['name']:
            raise ValueError('Missing language name')
        languages[code] = item
    if data['schema'] != 1 or data['default'] not in languages or languages[data['default']]['catalog'] is not None:
        raise ValueError('The default language must provide source-text fallback')
    return data['default'], languages


DEFAULT_LANGUAGE, LANGUAGES = load_languages()


def match_language(tag):
    """Match the first Windows preferred UI language; unsupported -> source language."""
    tag = tag.replace('_', '-').lower()
    for code, item in LANGUAGES.items():
        if tag in (code.lower(), item['locale'].lower()):
            return code
    base = tag.split('-')[0]
    return next((code for code in LANGUAGES if code.lower() == base), DEFAULT_LANGUAGE)


def load_errors(path=None):
    data = json.loads((path or DIRECTORY / 'errors.json').read_text(encoding='utf-8'))
    if data['schema'] != 1:
        raise ValueError('Unsupported error registry')
    errors = data['errors']
    for error_id, item in errors.items():
        if not re.fullmatch(r'E_[A-Z0-9_]{1,80}', error_id):
            raise ValueError('Invalid error ID')
        for field in ('source', 'public'):
            for _, name, spec, conversion in Formatter().parse(item.get(field, item['source'])):
                if name is not None and (not name.isidentifier() or not re.fullmatch(r'(?:\.[0-6]f)?', spec)
                                         or conversion not in (None, 's', 'r', 'a')):
                    raise ValueError('Unsupported error parameter format')
                if field == 'public' and name is not None:
                    raise ValueError('Public worker errors must not include private parameters')
    return errors


ERRORS = load_errors()
ERRORS_BY_SOURCE = {item['source']: key for key, item in ERRORS.items()}
