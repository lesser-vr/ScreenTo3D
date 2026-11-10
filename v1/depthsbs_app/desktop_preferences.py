"""Validated user selections; never persist sources, artifacts or license consent."""
from .messages import ErrorMessage as E

from PySide6.QtCore import QSettings

from .config import DEFAULT_MODE_MODELS, MODE_MODEL_CHOICES
from .stereo_layout import LAYOUTS


class DesktopPreferences:
    def __init__(self, store=None, *, portable=False):
        self.store = store if store is not None else QSettings('DepthSBS', 'DepthSBS')
        self.portable = portable

    def selection(self, scope, modes):
        mode = self.store.value(f'{scope}/mode', 'performance')
        if not isinstance(mode, str) or mode not in modes:
            mode = 'performance'
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
