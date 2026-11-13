"""Validated user selections; never persist sources, artifacts or license consent."""
from .messages import ErrorMessage as E

from PySide6.QtCore import QSettings

from .config import DEFAULT_MODE_MODELS, MODE_MODEL_CHOICES
from .stereo_layout import LAYOUTS
from .user_data import settings_file
from .portable_settings import migrate_settings


class DesktopPreferences:
    def __init__(self, store=None, *, portable=False):
        if store is None:
            from .user_data import _check,data_root
            _check(settings_file(),data_root())
            if settings_file().exists() and settings_file().stat().st_size>1024**2:
                raise OSError(E('E_SETTINGS_FILE_INVALID'))
        self.store = store if store is not None else QSettings(str(settings_file()),QSettings.IniFormat)
        self.store.setFallbacksEnabled(False)
        self.store.allKeys()
        if self.store.status()!=QSettings.NoError:raise OSError(E('E_SETTINGS_FILE_INVALID'))
        self.portable = portable

    def selection(self, scope, modes):
        default_mode='balanced' if scope=='file' else 'performance'
        mode = self.store.value(f'{scope}/mode', default_mode)
        if not isinstance(mode, str) or mode not in modes:
            mode = default_mode
        model = self.store.value(f'{scope}/model', DEFAULT_MODE_MODELS[mode])
        if (not isinstance(model, str) or model not in MODE_MODEL_CHOICES[mode]
                or self.portable and model == 'ovda-small-c16'):
            model = DEFAULT_MODE_MODELS[mode]
        layout = self.store.value(f'{scope}/stereoLayout', 'half-tb')
        if not isinstance(layout, str) or layout not in LAYOUTS:
            layout = 'half-tb'
        return dict(mode=mode, model=model, stereo_layout=layout)

    def remember(self, scope, mode, model, layout):
        if scope not in ('live', 'file') or model not in MODE_MODEL_CHOICES.get(mode, ()) or layout not in LAYOUTS:
            raise ValueError(E('E_SETTINGS_SELECTION_INVALID'))
        for key, value in (('mode', mode), ('model', model), ('stereoLayout', layout)):
            self.store.setValue(f'{scope}/{key}', value)
        self.store.sync()
        if self.store.status() != QSettings.NoError:
            raise OSError(E('E_SETTINGS_WRITE_FAILED'))
