import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: box
    required property string feature
    readonly property Theme theme: Theme {}
    readonly property var installer: desktop.modelDownloads
    readonly property bool missing: desktop.missingModels[feature] === true
    readonly property bool working: feature !== "" && installer.activeKey === feature
    readonly property bool recent: feature !== "" && installer.lastKey === feature
    readonly property string installAction: installer.installAction(feature)
    visible: missing || working || recent
    Layout.fillWidth: true
    spacing: 6
    Label {
        visible: box.missing
        text: box.installer.description(box.feature)
        color: box.theme.ink; wrapMode: Text.WordWrap; Layout.fillWidth: true
    }
    Label {
        visible: box.recent
        text: box.installer.status + (box.working && box.installer.percentage >= 0 ? " · " + box.installer.percentage + "%" : "")
        color: box.theme.muted; wrapMode: Text.WordWrap; Layout.fillWidth: true
    }
    ProgressBar {
        visible: box.working; Layout.fillWidth: true
        from: 0; to: 100; value: box.installer.percentage
        indeterminate: box.working && box.installer.percentage < 0
        Accessible.name: qsTr("Model installation progress")
    }
    RowLayout {
        visible: box.missing || box.working
        ActionButton {
            visible: !box.working && box.installAction !== ""; text: box.installAction; primary: true
            enabled: !desktop.busy; onClicked: box.installer.begin(box.feature, false)
        }
        ActionButton {
            visible: !box.working; text: qsTr("Install from file"); enabled: !desktop.busy; primary: box.installAction === ""
            onClicked: box.installer.begin(box.feature, true)
        }
        ActionButton { visible: box.working; text: qsTr("Cancel installation"); onClicked: box.installer.cancel() }
    }
}
