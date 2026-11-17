"""One non-blocking native error window owned by the desktop shell."""

from .messages import Message as M, ErrorMessage, as_error
from .localization import render
from .error_journal import record_error
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout


class LiveErrorDialog(QDialog):
    def __init__(self, owner):
        super().__init__()
        self.setObjectName("liveErrorDialog")
        self.title_source = M('3D error')
        self.message_source = ''
        self.setWindowTitle(render(self.title_source))
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint)
        self.setWindowModality(Qt.WindowModal)
        self.resize(620, 280)
        self.setMinimumSize(360, 200)
        self.setStyleSheet("""
            QDialog { background: #f5f5f7; }
            QPlainTextEdit { background: white; color: #25262a;
                border: 1px solid #d3d6dc; border-radius: 8px; padding: 10px;
                selection-background-color: #0067d9; selection-color: white; }
            QPushButton { background: white; color: #25262a; border: 1px solid #d3d6dc;
                border-radius: 7px; padding: 7px 20px; min-width: 64px; }
            QPushButton:hover { background: #eceef2; }
            QPushButton:focus { border: 2px solid #0067d9; }
        """)
        self.winId()  # A separate native window, not a QML overlay.
        self.windowHandle().setTransientParent(owner)
        owner.destroyed.connect(self.deleteLater)
        self.text = QPlainTextEdit(self)
        self.text.setObjectName("liveErrorText")
        self.text.setReadOnly(True)
        buttons = QDialogButtonBox(parent=self)
        self.close_button = buttons.addButton(render(M('Close')), QDialogButtonBox.RejectRole)
        self.close_button.setObjectName("closeLiveError")
        self.close_button.setText(render(M('Close')))
        self.close_button.setDefault(True)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.text)
        layout.addWidget(buttons)
        for target in (self, self.text, self.text.viewport(), self.close_button):
            target.installEventFilter(self)

    def showError(self, message, title=M('3D error')):
        from .capture_sources import exclude_preview

        self.title_source = title
        self.message_source = as_error(message)
        self.retranslate()
        # Preserve the report even if capture protection prevents showing it.
        # Language changes only retranslate the window and never add records.
        try:
            record_error(self.message_source, title=render(title),
                         message=render(self.message_source), displayed_text=self.text.toPlainText())
        except Exception:
            pass  # Error-history failures must not suppress the original window.
        if not exclude_preview(self.winId()):
            self.hide()
            return False
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()
        self.close_button.setFocus()
        return True

    def retranslate(self):
        self.setWindowTitle(render(self.title_source))
        self.close_button.setText(render(M('Close')))
        error=self.message_source
        if not error:
            self.text.clear()
            return
        text=f'{render(M("Error ID"))}: {error.error_id}\n\n{render(error)}'
        # Keep third-party diagnostics opaque, including filenames and codes.
        details=[error.details]
        details.extend(f'[{value.error_id}] {value}\n{value.details}'.rstrip()
                       for value in error.values.values() if isinstance(value,ErrorMessage))
        details=[detail for detail in details if detail and detail!=str(error)]
        if details:
            text+='\n\n'+render(M('Details'))+':\n'+'\n'.join(details)
        self.text.setPlainText(text)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.ShortcutOverride, QEvent.KeyPress) and event.matches(QKeySequence.Copy):
            if event.type() == QEvent.KeyPress:
                QApplication.clipboard().setText(self.text.toPlainText())
            event.accept()
            return True
        return super().eventFilter(watched, event)
