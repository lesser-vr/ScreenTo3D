"""Validated user selections; never persist sources, artifacts or license consent."""
from .messages import ErrorMessage as E

from PySide6.QtCore import QSettings

from .config import DEFAULT_MODE_MODELS, MODE_MODEL_CHOICES
from .stereo_layout import LAYOUTS


def migrate_settings(current,*legacies):
    """Adopt only owned missing values; retain old settings for older versions."""
    keys=['ui/language']+[f'{scope}/{key}' for scope in ('live','file')
                          for key in ('mode','model','stereoLayout')]
    current.sync()
    if current.status()!=QSettings.NoError:
        raise OSError(E('E_SETTINGS_MIGRATION'))
    for legacy in legacies:
        legacy.sync()
        if legacy.status()!=QSettings.NoError:raise OSError(E('E_SETTINGS_MIGRATION'))
        for key in keys:
            if not current.contains(key) and legacy.contains(key):
                current.setValue(key,legacy.value(key))
    current.sync()
    if current.status()!=QSettings.NoError:raise OSError(E('E_SETTINGS_MIGRATION'))
    return current


class DesktopPreferences:
    def __init__(self, store=None, *, portable=False):
        self.store = store if store is not None else migrate_settings(
            QSettings('ScreenTo3D','ScreenTo3D'),QSettings('StereoTo3D','StereoTo3D'),QSettings('DepthSBS','DepthSBS'))
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
