"""Normal-window placement only; never stores captured content or source titles."""
import json
import os
from pathlib import Path

from PySide6.QtCore import QRect


def fit_rect(rect, available):
    """Keep the complete client rectangle, including its top edge, on screen."""
    width = min(max(320, rect.width()), available.width())
    height = min(max(180, rect.height()), max(1, available.height() - 40))
    left = min(max(rect.x(), available.x()), available.right() - width + 1)
    top = min(max(rect.y(), available.y() + 32), available.bottom() - height + 1)
    return QRect(left, top, width, height)


class OutputPlacement:
    def __init__(self, path):
        self.path = Path(path)
        self.screen_name = ""
        self.rect = QRect(80, 80, 1280, 720)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            values = data["rect"]
            if (not isinstance(data["screen"], str) or len(values) != 4
                    or any(type(v) is not int or abs(v) > 100000 for v in values)
                    or min(values[2:]) <= 0):
                raise ValueError("Invalid saved placement")
            self.rect = QRect(*values)
            self.screen_name = data["screen"]
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def screen_index(self, screens, preferred=None):
        for index, screen in enumerate(screens):
            if screen.name() == self.screen_name:
                return index
        return screens.index(preferred) if preferred in screens else 0

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(dict(screen=self.screen_name, rect=[
                self.rect.x(), self.rect.y(), self.rect.width(), self.rect.height()
            ])), encoding="utf-8")
            os.replace(temp, self.path)
        except OSError:
            # An optional UI preference must not interrupt session cleanup.
            pass
