"""Review and save a single sanitized error report from the desktop."""
from pathlib import Path
from threading import Thread

from PySide6.QtCore import QIODevice, QSaveFile, QStandardPaths, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QLabel, QLineEdit,
    QListWidget, QPlainTextEdit, QVBoxLayout,
)

from .error_journal import read_recent_reports
from .error_report import ACTIVITIES, report_text
from .localization import render
from .messages import Message as M
from .report_pc import collect_pc_info


class ErrorReportDialog(QDialog):
    pcInfoReady = Signal(object)

    def __init__(self):
        super().__init__()
        self.setObjectName('errorReportDialog')
        self.setWindowModality(Qt.WindowModal)
        self.resize(660, 560)
        self.entries = []
        self.history_mode = False
        self.partial = False
        self._pc_info = None
        self._collecting_pc = False

        self.history = QListWidget()
        self.history.setObjectName('errorReportHistory')
        self.history.setMaximumHeight(140)
        self.intro = QLabel()
        self.intro.setWordWrap(True)
        self.note_label = QLabel()
        self.note = QLineEdit()
        self.note.setObjectName('errorReportNote')
        self.note.setMaxLength(500)
        self.note_label.setBuddy(self.note)
        self.diagnostics = QCheckBox()
        self.diagnostics.setObjectName('includeErrorDiagnostics')
        self.include_pc = QCheckBox()
        self.include_pc.setObjectName('includeReportPcInfo')
        self.include_pc.setChecked(True)
        self.preview = QPlainTextEdit(readOnly=True)
        self.preview.setObjectName('errorReportPreview')
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.saved = False
        self.save_failed = False
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        self.save_button = buttons.button(QDialogButtonBox.Save)
        self.save_button.setObjectName('saveErrorReport')
        self.save_button.setAutoDefault(False)
        self.close_button = buttons.button(QDialogButtonBox.Close)
        self.close_button.setDefault(True)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        for widget in (self.history, self.intro, self.note_label, self.note, self.diagnostics,
                       self.include_pc, self.preview, self.status, buttons):
            layout.addWidget(widget)
        layout.setStretchFactor(self.preview, 1)
        self.history.currentRowChanged.connect(self.select)
        self.note.textChanged.connect(self.refresh_preview)
        self.diagnostics.toggled.connect(self.refresh_preview)
        self.include_pc.toggled.connect(self.refresh_preview)
        self.pcInfoReady.connect(self._receive_pc_info, Qt.QueuedConnection)

    def _request_pc_info(self):
        if self._collecting_pc:
            return
        self._collecting_pc = True

        def work():
            info = collect_pc_info()
            try:
                self.pcInfoReady.emit(info)
            except RuntimeError:
                pass  # The application closed while Windows was queried.

        Thread(target=work, name='ScreenTo3D report PC info', daemon=True).start()

    @Slot(object)
    def _receive_pc_info(self, info):
        self._pc_info = info
        self._collecting_pc = False
        if self.include_pc.isChecked():
            self.refresh_preview()

    @property
    def selected(self):
        row = self.history.currentRow()
        if 0 <= row < len(self.entries):
            return self.entries[row]
        return None

    def open_history(self, owner):
        entries, partial = read_recent_reports()
        return self.present(owner, entries, history=True, partial=partial)

    def open_report(self, owner, report):
        return self.present(owner, [report] if report else [])

    def present(self, owner, entries, *, history=False, partial=False):
        from .capture_sources import exclude_preview
        # Set ownership and affinity before displaying anything from the journal.
        self.winId()
        self.windowHandle().setTransientParent(owner)
        if not exclude_preview(self.winId()):
            self.hide()
            return False
        if not self._collecting_pc:
            self._pc_info = None
        self.entries = entries
        self.history_mode = history
        self.partial = partial
        self.history.setVisible(history)
        self.rebuild_history(0)
        self.select(self.history.currentRow())
        self.retranslate()
        self.show()
        self.raise_()
        self.activateWindow()
        (self.history if history and entries else self.close_button).setFocus()
        return True

    def rebuild_history(self, row):
        self.history.blockSignals(True)
        try:
            self.history.clear()
            for report in self.entries:
                self.history.addItem(
                    f"{report['time'].isoformat(sep=' ', timespec='milliseconds')[:23]}  ·  "
                    f"{render(ACTIVITIES[report['activity']])}  ·  {report['error_id']}"
                )
            self.history.setCurrentRow(row if self.entries else -1)
        finally:
            self.history.blockSignals(False)

    def retranslate(self):
        self.setWindowTitle(render(M('Recent errors') if self.history_mode else M('ScreenTo3D error report')))
        self.history.setAccessibleName(render(M('Recent errors')))
        self.intro.setText(render(M('Review the contents before sharing.')))
        self.note_label.setText(render(M('What happened just before the error?')))
        self.note.setAccessibleName(self.note_label.text())
        self.diagnostics.setText(render(M('Include diagnostics from the last 60 seconds')))
        self.include_pc.setText(render(M('Include PC information')))
        self.preview.setAccessibleName(render(M('Report preview')))
        self.save_button.setText(render(M('Save report…')))
        self.close_button.setText(render(M('Close')))
        self.rebuild_history(self.history.currentRow())
        self.refresh_preview()

    def select(self, _row):
        self.note.clear()
        self.diagnostics.setChecked(False)
        self.refresh_preview()

    def refresh_preview(self, *_):
        self.saved = self.save_failed = False
        report = self.selected
        has_diagnostics = bool(report and (report['samples'] or report['events']))
        self.diagnostics.setVisible(has_diagnostics)
        for widget in (self.intro, self.note_label, self.note, self.include_pc):
            widget.setVisible(report is not None)
        include_pc = report is not None and self.include_pc.isChecked()
        waiting_for_pc = include_pc and self._pc_info is None
        self.save_button.setEnabled(report is not None and not waiting_for_pc)
        if report:
            text = report_text(
                report, render, note=self.note.text(),
                include_diagnostics=self.diagnostics.isChecked(),
                pc_info=self._pc_info if include_pc else None,
            )
            if waiting_for_pc:
                self._request_pc_info()
                text += '\n' + render(M('Collecting PC information…')) + '\n'
        else:
            text = render(M('No recent errors.')) if not self.partial else ''
        self.preview.setPlainText(text)
        self.update_status()

    def update_status(self):
        if self.save_failed:
            self.status.setText(render(M('Could not save the report. Choose another location and try again.')))
        elif self.saved:
            self.status.setText(render(M('Report saved.')))
        elif self.partial:
            self.status.setText(render(M('Some error records could not be read.')))
        else:
            self.status.clear()
        self.status.setVisible(bool(self.status.text()))

    def save(self):
        report = self.selected
        if report is None or not self.save_button.isEnabled():
            return
        text = self.preview.toPlainText()
        stamp = report['time'].strftime('%Y%m%d-%H%M%S')
        filename = f"ScreenTo3D-{report['error_id']}-{stamp}.txt"
        documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        path, _ = QFileDialog.getSaveFileName(
            self, render(M('Save report…')), str(Path(documents) / filename),
            render(M('Text files (*.txt)')),
        )
        if not path:
            return
        if not Path(path).suffix:
            path += '.txt'
        # Protect the app's diagnostic history even if a user selects an existing
        # log using the file picker. Export is deliberately a plain text file.
        try:
            target = Path(path).resolve()
            self.saved = target.suffix.lower() == '.txt' and save_report(str(target), text)
        except (OSError, RuntimeError):
            self.saved = False
        self.save_failed = not self.saved
        self.update_status()


def save_report(path, text):
    output = QSaveFile(path)
    data = text.encode('utf-8')
    if not output.open(QIODevice.WriteOnly):
        return False
    if output.write(data) != len(data):
        output.cancelWriting()
        return False
    return output.commit()
