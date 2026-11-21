"""Single source of application shortcut keys and Win32 registration values."""
from dataclasses import dataclass


@dataclass(frozen=True)
class GlobalShortcut:
    keys: str
    identifier: int
    key: int
    modifiers: int = 0x4003  # MOD_NOREPEAT | MOD_CONTROL | MOD_ALT


FULLSCREEN = GlobalShortcut('Ctrl+Alt+Enter', 0x5311, 0x0D)
VFG = GlobalShortcut('Ctrl+Alt+S', 0x5310, 0x53)
FULLSCREEN_EXIT = GlobalShortcut('F11', 0x5312, 0x7A, modifiers=0x4000)
LOCAL_FULLSCREEN = FULLSCREEN_EXIT.keys
LOCAL_EXIT = 'Esc'
