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
        Label { text: "실시간 출력 설정"; color: options.theme.ink; font.pixelSize: 22; font.bold: true; Layout.margins: 24 }
        ColumnLayout {
            Layout.fillWidth: true; Layout.leftMargin: 24; Layout.rightMargin: 24; spacing: 12
            Copy { text: live.active ? "깊이 모델과 FPS 제한을 변경하려면 SBS를 중지하세요." : "깊이 모델과 FPS 제한은 다음 SBS 실행에 적용됩니다." }
            RowLayout {
                spacing: 6
                Label { text: "깊이 모델"; color: options.theme.ink }
                HelpButton { objectName: "liveModelHelp"; Accessible.name: "깊이 모델과 정밀도 도움말"; helpText: live.depthModelHelp }
            }
            ChoicePicker {
                objectName: "livePolicy"; enabled: !desktop.busy
                model: live.depthChoices; textRole: "label"; valueRole: "key"
                currentIndex: live.depthChoices.map(function(m) { return m.mode + "/" + m.model }).indexOf(live.liveMode + "/" + live.liveModel)
                onActivated: { live.selectDepthModel(currentValue); live.rememberSelection() }
                Accessible.name: "깊이 모델"
            }
            CheckOption { visible: live.liveModel === "ovda-small-c16"; enabled: !live.active; text: "개인·비상업적 사용 및 라이선스 조건 확인"; checked: live.ovdaConfirmed; onClicked: live.setOvdaConfirmed(checked) }
            ModelInstall { feature: live.liveModel }
            RowLayout {
                Label { text: "입체감"; color: options.theme.ink; Layout.fillWidth: true }
                Label { text: live.depthStrength.toFixed(2) + "×"; color: options.theme.muted }
                ActionButton { objectName: "resetLiveStrength"; text: "기본값"; enabled: !live.active; onClicked: live.resetStrength() }
            }
            Slider {
                id: strength; objectName: "liveStrength"; Layout.fillWidth: true
                enabled: !options.liveController.active; from: 0.25; to: 2; stepSize: 0.25
                value: options.liveController.depthStrength; onMoved: options.liveController.setStrength(value); Accessible.name: "입체감"
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
            CheckOption { objectName: "cursorIncluded"; text: "커서 포함"; enabled: !live.active; checked: live.cursorIncluded; onClicked: live.setCursor(checked) }
            RowLayout {
                visible: live.vfgConfigurable
                Layout.fillWidth: true; spacing: 6
                CheckOption {
                    objectName: "vfgEnabled"; text: "프레임 보간 (VFG)"
                    enabled: !live.stoppingNow && !live.vfgSwitching && (!desktop.busy || live.active) && (live.vfgEnabled || live.vfgUnavailableReason.length === 0)
                    checked: live.vfgEnabled; onClicked: live.setVfg(checked)
                    Accessible.name: "프레임 보간 VFG"
                }
                HelpButton {
                    objectName: "vfgHelp"; Accessible.name: "프레임 보간 VFG 도움말"
                    helpText: "중간 프레임을 추가해 움직임을 부드럽게 합니다. 지연과 GPU 사용량이 늘 수 있습니다."
                        + "\n\n" + live.vfgShortcut
                        + (live.vfgUnavailableReason.length > 0 ? "\n\n" + live.vfgUnavailableReason : "")
                        + (live.vfgSwitching ? "\n\nVFG 전환 중…" : "")
                }
                Item { Layout.fillWidth: true }
            }
            ModelInstall { feature: live.vfgConfigurable && live.vfgEnabled ? "vfg" : "" }
            Label { text: "출력 FPS 제한"; color: options.theme.ink }
            ChoicePicker { objectName: "livePresentationHz"; enabled: !live.active; model: ["30 FPS", "60 FPS · 기본", "무제한"]; currentIndex: [30, 60, 0].indexOf(live.presentationHz); onActivated: live.setPresentationHz([30, 60, 0][currentIndex]); Accessible.name: "출력 FPS 제한" }
            Label { text: "입체 출력 형식"; color: options.theme.ink }
            StereoLayoutPicker { objectName: "liveStereoLayout"; enabled: !live.active; currentIndex: keys.indexOf(live.stereoLayout); onActivated: { live.setStereoLayout(keys[currentIndex]); live.rememberSelection() } }
            Copy { text: "3D 재생 장치에서도 같은 형식을 선택하세요. Half 형식은 한쪽 축의 해상도를 절반으로 줄입니다." }
            CheckOption { objectName: "fullscreenStatsToggle"; text: "전체 화면에 성능 정보 표시"; checked: options.fullscreenStats; onClicked: options.fullscreenStatsRequested(checked) }
            ActionButton { objectName: "openSettings"; text: "설정과 진단"; onClicked: options.diagnosticsRequested() }
            Item { height: 16 }
        }
    }
}
