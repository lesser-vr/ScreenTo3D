import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

FocusScrollView {
    id: options
    readonly property Theme theme: Theme {}
    property var liveController: live
    contentWidth: availableWidth
    component Copy: Label { color: options.theme.muted; wrapMode: Text.WordWrap; Layout.fillWidth: true }
    ColumnLayout {
        width: parent.width; spacing: 16
        Label { text: "화질과 입체감"; color: options.theme.ink; font.pixelSize: 22; font.bold: true; Layout.margins: 24 }
        ColumnLayout {
            Layout.fillWidth: true; Layout.leftMargin: 24; Layout.rightMargin: 24; spacing: 12
            Copy { text: live.active ? "변경하려면 SBS를 중지하세요." : "설정은 다음 SBS 실행에 적용됩니다." }
            Label { text: "처리 모드"; color: options.theme.ink }
            ChoicePicker { objectName: "livePolicy"; enabled: !live.active; model: live.liveModes; textRole: "label"; valueRole: "key"; currentIndex: live.liveModes.map(function(m) { return m.key }).indexOf(live.liveMode); onActivated: live.setMode(currentValue); Accessible.name: "처리 모드" }
            Copy { text: "선택한 모델 · " + live.liveModelLabel; font.pixelSize: 12 }
            ChoicePicker { objectName: "liveModel"; visible: live.liveModels.length > 1; enabled: !live.active; model: live.liveModels; textRole: "label"; valueRole: "key"; currentIndex: live.liveModels.map(function(m) { return m.key }).indexOf(live.liveModel); onActivated: live.setLiveModel(currentValue); Accessible.name: "영상 품질 모델" }
            CheckOption { visible: live.liveModel === "ovda-small-c16"; enabled: !live.active; text: "개인·비상업적 사용 및 라이선스 조건 확인"; checked: live.ovdaConfirmed; onClicked: live.setOvdaConfirmed(checked) }
            RowLayout {
                Label { text: "입체감"; color: options.theme.ink; Layout.fillWidth: true }
                Label { text: live.depthStrength.toFixed(2) + "×"; color: options.theme.muted }
                ActionButton { text: "기본값"; enabled: !live.active; onClicked: live.setStrength(1) }
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
            Item { height: 16 }
        }
    }
}
