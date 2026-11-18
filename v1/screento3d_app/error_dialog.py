"""One non-blocking native error window owned by the desktop shell."""

from .messages import Message as M, ErrorMessage, as_error
from .localization import render
from .error_journal import make_error_record, record_error
from .error_report import prepare_report
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout


class LiveErrorDialog(QDialog):
    def __init__(self, owner):
        super().__init__()
        self.setObjectName("liveErrorDialog")
        self.title_source = M('3D error')
        self.message_source = ''
        self.diagnostic_context = None
        self.report_entry = None
        self._report_dialog = None
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
        self.report_button = buttons.addButton(render(M('Prepare report…')), QDialogButtonBox.ActionRole)
        self.report_button.setObjectName('prepareErrorReport')
        self.report_button.setAutoDefault(False)
        self.report_button.clicked.connect(self.open_report)
        self.close_button = buttons.addButton(render(M('Close')), QDialogButtonBox.RejectRole)
        self.close_button.setObjectName("closeLiveError")
        self.close_button.setText(render(M('Close')))
        self.close_button.setDefault(True)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.text)
        self.report_status = QLabel(wordWrap=True)
        self.report_status.hide()
        layout.addWidget(self.report_status)
        layout.addWidget(buttons)
        for target in (self, self.text, self.text.viewport(), self.report_button, self.close_button):
            target.installEventFilter(self)

    def showError(self, message, title=M('3D error'), *, activity=None):
        from .capture_sources import exclude_preview

        self.title_source = title
        self.report_status.hide()
        self.message_source = as_error(message)
        self.retranslate()
        # Preserve the report even if capture protection prevents showing it.
        # Language changes only retranslate the window and never add records.
        diagnostic_context = self.diagnostic_context
        self.diagnostic_context = None
        self.report_entry = None
        try:
            entry = make_error_record(
                self.message_source, title=render(title), message=render(self.message_source),
                displayed_text=self.text.toPlainText(), diagnostics=diagnostic_context, activity=activity,
            )
            self.report_entry = prepare_report(entry)
            record_error(self.message_source, entry=entry)
        except Exception:
            pass  # Error-history failures must not suppress the original window.
        self.report_button.setEnabled(self.report_entry is not None)
        if not exclude_preview(self.winId()):
            self.hide()
            return False
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()
        self.close_button.setFocus()
        return True

    def report_dialog(self):
        if self._report_dialog is None:
            from .error_report_dialog import ErrorReportDialog
            self._report_dialog = ErrorReportDialog()
            self._report_dialog.setStyleSheet(self.styleSheet())
            self.destroyed.connect(self._report_dialog.deleteLater)
        return self._report_dialog

    def open_report(self):
        if self.report_dialog().open_report(self.windowHandle(), self.report_entry):
            self.report_status.hide()
        else:
            self.report_status.setText(render(M('Could not open the report window.')))
            self.report_status.show()

    def retranslate(self):
        self.setWindowTitle(render(self.title_source))
        self.report_button.setText(render(M('Prepare report…')))
        if not self.report_status.isHidden():
            self.report_status.setText(render(M('Could not open the report window.')))
        if self._report_dialog is not None:
            self._report_dialog.retranslate()
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
