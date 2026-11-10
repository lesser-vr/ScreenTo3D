"""GUI-owned Qt translation; model and capture workers keep language-free messages."""
from functools import wraps
from pathlib import Path
from string import Formatter

from PySide6.QtCore import QObject, Property, Signal, Slot, QCoreApplication, QLocale, QTranslator, QLibraryInfo, QSettings, Qt

from .messages import Message as M, Message, ErrorMessage, JoinedMessage, message_value
from .catalogs import DEFAULT_LANGUAGE, LANGUAGES, match_language, DIRECTORY


class _LocaleFormatter(Formatter):
    def format_field(self, value, spec):
        if isinstance(value,float) and spec.endswith('f') and spec.startswith('.') and spec[1:-1].isdigit():
            return QLocale().toString(value,'f',int(spec[1:-1]))
        return super().format_field(value,spec)


def render(value):
    if isinstance(value,BaseException):
        value=message_value(value)
    if isinstance(value,Message):
        if isinstance(value,ErrorMessage):
            source=QCoreApplication.translate('PublicErrors' if value.public else 'Errors',value.error_id)
            if source==value.error_id:
                source=value.source
        else:
            source=QCoreApplication.translate('ScreenTo3D',value.source)
        return _LocaleFormatter().vformat(source,(),{k:render(v) for k,v in value.values.items()})
    if isinstance(value,JoinedMessage):
        return ''.join(str(render(part)) for part in value.parts)
    if isinstance(value,list):
        return [render(item) for item in value]
    if isinstance(value,dict):
        return {key:render(item) for key,item in value.items()}
    return value


def localized(function):
    @wraps(function)
    def getter(*args,**kwargs):
        return render(function(*args,**kwargs))
    return getter


def resolve_language(choice, system=None):
    if choice in LANGUAGES:
        return choice
    languages=(system or QLocale.system()).uiLanguages()
    return match_language(languages[0]) if languages else DEFAULT_LANGUAGE


class LanguageManager(QObject):
    changed=Signal()
    errorOccurred=Signal(object)

    def __init__(self,preferences,parent=None):
        super().__init__(parent)
        self.preferences=preferences
        choice=preferences.store.value('ui/language','system')
        self.choice=choice if choice=='system' or choice in LANGUAGES else 'system'
        self.effective=DEFAULT_LANGUAGE
        self.translators=[]
        self.engine=None
        self.refresh=None
        self._apply()

    @Property(str,notify=changed)
    def selected(self):
        return self.choice

    @Property(str,notify=changed)
    def effectiveLanguage(self):
        return self.effective

    @Property(str,notify=changed)
    def localeName(self):
        if self.choice=='system':
            system=QLocale.system()
            if system.textDirection()==Qt.LeftToRight:
                return system.name()
        return LANGUAGES[self.effective]['locale'].replace('-','_')

    @Property(str,notify=changed)
    def uiLanguage(self):
        return LANGUAGES[self.effective]['locale']

    @Property('QVariantList',notify=changed)
    def choices(self):
        return [dict(key='system',label=render(M('System default'))),
                *(dict(key=key,label=item['name']) for key,item in LANGUAGES.items())]

    def _apply(self):
        app=QCoreApplication.instance()
        self.close()
        self.effective=resolve_language(self.choice)
        definition=LANGUAGES[self.effective]
        if definition['catalog']:
            translator=QTranslator(self)
            if translator.load(str(DIRECTORY/(definition['catalog']+'.qm'))):
                app.installTranslator(translator)
                self.translators.append(translator)
                base=Path(QLibraryInfo.path(QLibraryInfo.TranslationsPath))
                for name in definition.get('qt_catalogs',[]):
                    standard=QTranslator(self)
                    if standard.load(str(base/(name+'.qm'))):
                        app.installTranslator(standard)
                        self.translators.append(standard)
                    else:
                        standard.deleteLater()
            else:
                translator.deleteLater()
                self.effective=DEFAULT_LANGUAGE
        QLocale.setDefault(QLocale(self.localeName))
        app.setLayoutDirection(Qt.LeftToRight)

    def close(self):
        app=QCoreApplication.instance()
        for translator in self.translators:
            app.removeTranslator(translator)
            translator.deleteLater()
        self.translators.clear()

    @Slot(str)
    def setLanguage(self,choice):
        if (choice!='system' and choice not in LANGUAGES) or choice==self.choice:
            return
        old=self.choice
        self.preferences.store.setValue('ui/language',choice)
        self.preferences.store.sync()
        if self.preferences.store.status()!=QSettings.NoError:
            self.preferences.store.setValue('ui/language',old)
            self.errorOccurred.emit(ErrorMessage('E_SETTINGS_LANGUAGE_WRITE'))
            return
        self.choice=choice
        self._apply()
        if self.engine is not None:
            self.engine.setUiLanguage(self.uiLanguage)
            self.engine.retranslate()
        if self.refresh is not None:
            self.refresh()
        self.changed.emit()
