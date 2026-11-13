"""Optional legacy settings import. Normal launches never read the registry."""
from PySide6.QtCore import QSettings
from .messages import ErrorMessage as E
from .user_data import LEGACY_DIRECTORIES

OWNED_KEYS=['ui/language','SbsOutput/fullscreenStats']+[
    f'{scope}/{key}' for scope in ('live','file') for key in ('mode','model','stereoLayout')]


def read_legacy_settings():
    return _read_stores([QSettings(name,name) for name in LEGACY_DIRECTORIES])


def _read_stores(stores):
    values={}
    for store in stores:
        store.setFallbacksEnabled(False);store.sync()
        if store.status()!=QSettings.NoError:raise OSError(E('E_SETTINGS_MIGRATION'))
        for key in OWNED_KEYS:
            if key not in values and store.contains(key):values[key]=store.value(key)
    return values


def migrate_settings(current,*legacies):
    """Compatibility helper used only by explicit import callers."""
    current.sync()
    if current.status()!=QSettings.NoError:raise OSError(E('E_SETTINGS_MIGRATION'))
    adopt_settings(current,_read_stores(legacies))
    return current


def adopt_settings(store,values):
    for key,value in values.items():
        if key in OWNED_KEYS and not store.contains(key):store.setValue(key,value)
    store.sync()
    if store.status()!=QSettings.NoError:raise OSError(E('E_SETTINGS_MIGRATION'))
