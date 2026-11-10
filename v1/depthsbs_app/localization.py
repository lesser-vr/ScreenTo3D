"""GUI-owned Qt translation; model and capture workers keep language-free messages."""
from functools import wraps
from pathlib import Path
from string import Formatter

from PySide6.QtCore import QObject, Property, Signal, Slot, QCoreApplication, QLocale, QTranslator, QLibraryInfo, QSettings, Qt

from .messages import Message as M, Message, JoinedMessage, message_value


class _LocaleFormatter(Formatter):
    def format_field(self, value, spec):
        if isinstance(value,float) and spec.endswith('f') and spec.startswith('.') and spec[1:-1].isdigit():
            return QLocale().toString(value,'f',int(spec[1:-1]))
        return super().format_field(value,spec)


def render(value):
    if isinstance(value,BaseException):
        value=message_value(value)
    if isinstance(value,Message):
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
    if choice in ('ko','en'):
        return choice
    languages=(system or QLocale.system()).uiLanguages()
    return 'ko' if languages and QLocale(languages[0]).language()==QLocale.Korean else 'en'


class LanguageManager(QObject):
    changed=Signal()
    errorOccurred=Signal(object)

    def __init__(self,preferences,parent=None):
        super().__init__(parent)
        self.preferences=preferences
        choice=preferences.store.value('ui/language','system')
        self.choice=choice if choice in ('system','ko','en') else 'system'
        self.effective='en'
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
        return 'ko_KR' if self.effective=='ko' else 'en_US'

    @Property('QVariantList',notify=changed)
    def choices(self):
        return [dict(key='system',label=render(M('System default'))),
                dict(key='ko',label='한국어'),dict(key='en',label='English')]

    def _apply(self):
        app=QCoreApplication.instance()
        self.close()
        self.effective=resolve_language(self.choice)
        if self.effective=='ko':
            translator=QTranslator(self)
            if translator.load(str(Path(__file__).with_name('translations')/'screento3d_ko.qm')):
                app.installTranslator(translator)
                self.translators.append(translator)
                base=Path(QLibraryInfo.path(QLibraryInfo.TranslationsPath))
                for name in ('qtbase_ko','qtdeclarative_ko'):
                    standard=QTranslator(self)
                    if standard.load(str(base/(name+'.qm'))):
                        app.installTranslator(standard)
                        self.translators.append(standard)
                    else:
                        standard.deleteLater()
            else:
                translator.deleteLater()
                self.effective='en'
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
        if choice not in ('system','ko','en') or choice==self.choice:
            return
        old=self.choice
        self.preferences.store.setValue('ui/language',choice)
        self.preferences.store.sync()
        if self.preferences.store.status()!=QSettings.NoError:
            self.preferences.store.setValue('ui/language',old)
            self.errorOccurred.emit(M('Cannot save the language setting. Check access to the application settings.'))
            return
        self.choice=choice
        self._apply()
        if self.engine is not None:
            self.engine.setUiLanguage('ko-KR' if self.effective=='ko' else 'en-US')
            self.engine.retranslate()
        if self.refresh is not None:
            self.refresh()
        self.changed.emit()
