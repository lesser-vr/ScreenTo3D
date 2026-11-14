import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

FocusScrollView {
    signal diagnosticsRequested()
    property bool fullscreenStats: false
    signal fullscreenStatsRequested(bool enabled)
    id: options
    readonly property Theme theme: Theme {}
    property var liveController: live
    contentWidth: availableWidth
    component Copy: Label { color: options.theme.muted; wrapMode: Text.WordWrap; Layout.fillWidth: true }
    ColumnLayout {
        width: parent.width; spacing: 16
        Label { text: qsTr("Live output settings"); color: options.theme.ink; font.pixelSize: 22; font.bold: true; Layout.margins: 24 }
        ColumnLayout {
            Layout.fillWidth: true; Layout.leftMargin: 24; Layout.rightMargin: 24; spacing: 12
            Copy { text: live.active ? qsTr("Stop 3D to change the depth model or FPS limit.") : qsTr("The depth model and FPS limit apply to the next live 3D session.") }
            RowLayout {
                spacing: 6
                Label { text: qsTr("Depth model"); color: options.theme.ink }
                HelpButton { objectName: "liveModelHelp"; Accessible.name: qsTr("Depth model and precision help"); helpText: live.depthModelHelp }
            }
            ChoicePicker {
                objectName: "livePolicy"; enabled: !desktop.busy
                model: live.depthChoices; textRole: "label"; valueRole: "key"
                currentIndex: live.depthChoices.map(function(m) { return m.mode + "/" + m.model }).indexOf(live.liveMode + "/" + live.liveModel)
                onActivated: { live.selectDepthModel(currentValue); live.rememberSelection() }
                Accessible.name: qsTr("Depth model")
            }
            CheckOption { objectName: "ovdaConsent"; visible: live.liveModel === "ovda-small-c16"; enabled: !live.active; text: qsTr("I confirm personal, non-commercial use and the license terms"); checked: live.ovdaConfirmed; onClicked: live.setOvdaConfirmed(checked) }
            ModelInstall { feature: "trt-core" }
            ModelInstall { objectName: "liveGpuRuntimeInstall"; feature: desktop.gpuRuntimeKey }
            ModelInstall { feature: live.liveModel }
            RowLayout {
                Label { text: qsTr("Depth strength"); color: options.theme.ink; Layout.fillWidth: true }
                Label { text: live.depthStrength.toLocaleString(Qt.locale(i18n.localeName), "f", 2) + "×"; color: options.theme.muted }
                ActionButton { objectName: "resetLiveStrength"; text: qsTr("Reset"); enabled: !live.active; onClicked: live.resetStrength() }
            }
            Slider {
                id: strength; objectName: "liveStrength"; Layout.fillWidth: true
                enabled: !options.liveController.active; from: 0.25; to: 2; stepSize: 0.25
                value: options.liveController.depthStrength; onMoved: options.liveController.setStrength(value); Accessible.name: qsTr("Depth strength")
                background: Rectangle {
                    x: strength.leftPadding; y: strength.topPadding + strength.availableHeight / 2 - height / 2
                    implicitWidth: 200; implicitHeight: 4; width: strength.availableWidth; height: 4; radius: 2
                    color: options.theme.disabled
                    Rectangle { width: strength.visualPosition * parent.width; height: parent.height; radius: 2; color: strength.enabled ? options.theme.blue : options.theme.disabledInk }
                }
                handle: Rectangle {
                    x: strength.leftPadding + strength.visualPosition * (strength.availableWidth - width)
                    y: strength.topPadding + strength.availableHeight / 2 - height / 2
                    implicitWidth: 20; implicitHeight: 20; radius: 10; color: options.theme.surface
                    border.color: strength.activeFocus ? options.theme.blue : options.theme.border; border.width: strength.activeFocus ? 2 : 1
                }
            }
            CheckOption { objectName: "cursorIncluded"; text: qsTr("Include cursor"); enabled: !live.active; checked: live.cursorIncluded; onClicked: live.setCursor(checked) }
            RowLayout {
                visible: live.vfgConfigurable
                Layout.fillWidth: true; spacing: 6
                CheckOption {
                    objectName: "vfgEnabled"; text: qsTr("Frame interpolation (VFG)")
                    Layout.fillWidth: false
                    enabled: !live.stoppingNow && !live.vfgSwitching && (!desktop.busy || live.active) && (live.vfgEnabled || live.vfgUnavailableReason.length === 0)
                    checked: live.vfgEnabled; onClicked: live.setVfg(checked)
                    Accessible.name: qsTr("VFG frame interpolation")
                }
                HelpButton {
                    objectName: "vfgHelp"; Accessible.name: qsTr("VFG frame interpolation help")
                    helpText: qsTr("Adds intermediate frames for smoother motion. This may increase latency and GPU usage.")
                        + "\n\n" + live.vfgShortcut
                        + (live.vfgUnavailableReason.length > 0 ? "\n\n" + live.vfgUnavailableReason : "")
                        + (live.vfgSwitching ? qsTr("\n\nSwitching VFG…") : "")
                }
                Item { Layout.fillWidth: true }
            }
            ModelInstall { feature: live.vfgConfigurable && live.vfgEnabled ? "vfg" : "" }
            Label { text: qsTr("Output FPS limit"); color: options.theme.ink }
            ChoicePicker { objectName: "livePresentationHz"; enabled: !live.active; model: ["30 FPS", qsTr("60 FPS · Default"), qsTr("Unlimited")]; currentIndex: [30, 60, 0].indexOf(live.presentationHz); onActivated: live.setPresentationHz([30, 60, 0][currentIndex]); Accessible.name: qsTr("Output FPS limit") }
            Label { text: qsTr("Stereo layout"); color: options.theme.ink }
            StereoLayoutPicker { objectName: "liveStereoLayout"; enabled: !live.active; currentIndex: keys.indexOf(live.stereoLayout); onActivated: { live.setStereoLayout(keys[currentIndex]); live.rememberSelection() } }
            Copy { text: qsTr("Select the same layout on your 3D playback device. Half layouts halve resolution along one axis.") }
            CheckOption { objectName: "fullscreenStatsToggle"; text: qsTr("Show performance information in fullscreen"); checked: options.fullscreenStats; onClicked: options.fullscreenStatsRequested(checked) }
            Copy { text: qsTr("Use the original window for keyboard and mouse input. Drag the 3D title bar or right-click the 3D window to manage it.") }
            RowLayout {
                Layout.fillWidth: true; spacing: 6
                ActionButton { objectName: "toggleOutputFullscreen"; text: qsTr("Toggle 3D fullscreen"); enabled: live.active && !live.stoppingNow; onClicked: live.toggleOutputFullscreen() }
                HelpButton { Accessible.name: qsTr("3D window controls help"); helpText: live.outputShortcut + "\n\n" + qsTr("F11 and Esc work while the 3D window is active. Window controls return focus to the original window when finished.") }
            }
            ActionButton { objectName: "openSettings"; text: qsTr("Settings and diagnostics"); onClicked: options.diagnosticsRequested() }
            Item { height: 16 }
        }
    }
}
