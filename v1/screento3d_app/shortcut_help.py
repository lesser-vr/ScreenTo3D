"""Localized, shared shortcut guide; notifications never open an error dialog."""
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from .localization import render
from .messages import Message as M
from .shortcut_keys import FULLSCREEN, VFG, LOCAL_FULLSCREEN, LOCAL_EXIT


class ShortcutHelp(QObject):
    changed = Signal()

    def __init__(self, live, vfg_hotkey):
        super().__init__(live)
        self.live, self.vfg_hotkey = live, vfg_hotkey
        self.snapshot = None
        self.notice_source = ''
        self.reported = set()
        self.notice_timer = QTimer(self)
        self.notice_timer.setSingleShot(True)
        self.notice_timer.setInterval(6000)
        self.notice_timer.timeout.connect(self.clear_notice)
        live.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        live, policy = self.live, self.live.output_policy
        state = (bool(live.active), bool(live.stoppingNow), bool(live.vfgSwitching),
                 bool(policy and policy.state), bool(policy and policy.registered),
                 bool(self.vfg_hotkey.registered), bool(live.vfgConfigurable))
        if not state[0] and not state[2]:
            self.reported.clear()
            self.clear_notice()
        elif state[3] and live.hasFrame:
            failures = []
            if not state[4]: failures.append(FULLSCREEN.keys)
            if state[6] and not state[5]: failures.append(VFG.keys)
            fresh = set(failures) - self.reported
            if fresh:
                self.reported.update(fresh)
                self.notice_source = M('Shortcut unavailable: {keys}. Open ? for controls.', keys=', '.join(failures))
                self.notice_timer.start()
                self.changed.emit()
        if state != self.snapshot:
            self.snapshot = state
            self.changed.emit()

    def clear_notice(self):
        self.notice_timer.stop()
        if self.notice_source:
            self.notice_source = ''
            self.changed.emit()

    @Property(str, notify=changed)
    def notice(self):
        return render(self.notice_source)

    @Property(str, constant=True)
    def fullscreenLocalKey(self):
        return LOCAL_FULLSCREEN

    @Property(str, constant=True)
    def exitKey(self):
        return LOCAL_EXIT

    @Property(str, constant=True)
    def vfgKey(self):
        return VFG.keys

    @Property(str, notify=changed)
    def fullscreenTitle(self):
        policy = self.live.output_policy
        if policy and policy.registered:
            return render(M('{keys} Fullscreen', keys=FULLSCREEN.keys))
        return render(M('Fullscreen'))

    @Property('QVariantList', notify=changed)
    def groups(self):
        live, policy = self.live, self.live.output_policy
        playing = bool(live.active and not live.stoppingNow)
        visible = bool(policy and policy.state)
        def row(keys, label, conflict=False, action='', action_label='', enabled=False, detail=''):
            return dict(keys=keys, label=render(label), conflict=conflict,
                        status=render(M('Unavailable · Check whether another app uses this shortcut.')) if conflict else '',
                        action=action, actionLabel=render(action_label), enabled=bool(enabled), detail=render(detail))
        global_rows = [row(FULLSCREEN.keys, M('Toggle fullscreen'),
                           visible and not policy.registered, 'fullscreen', M('Toggle fullscreen'), playing and visible)]
        if live.vfgConfigurable:
            reason = live.vfgUnavailableReason
            global_rows.append(row(VFG.keys, M('Toggle VFG'), not self.vfg_hotkey.registered,
                                   'vfg', M('Toggle VFG'), playing and not live.vfgSwitching
                                   and (live.vfgEnabled or not reason), reason if playing else ''))
        return [dict(title=render(M('While using the original window')), rows=global_rows),
                dict(title=render(M('When the 3D window is selected')), rows=[
                    row(LOCAL_FULLSCREEN, M('Toggle fullscreen, then return to the original window')),
                    row(LOCAL_EXIT, M('Exit fullscreen'))])]

    @Slot(str)
    def activate(self, action):
        if not self.live.active or self.live.stoppingNow:
            return
        if action == 'fullscreen':
            self.live.toggleOutputFullscreen()
        elif action == 'vfg' and not self.live.vfgSwitching:
            self.live.toggleVfg()
