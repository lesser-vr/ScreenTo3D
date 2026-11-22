import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: setup
    required property var mainWindow
    readonly property Theme theme: Theme {}
    readonly property var installer: desktop.modelDownloads
    objectName: "runtimeSetupWindow"
    title: qsTr("ScreenTo3D · Required components")
    width: 520; height: 420
    minimumWidth: 380; minimumHeight: Math.max(300, content.implicitHeight + 48)
    color: theme.window
    visible: installer.setupVisible
    transientParent: mainWindow
    onVisibleChanged: {
        if (visible && !desktop.protectWindow(setup)) installer.dismissSetup()
    }
    onClosing: installer.dismissSetup()
    ColumnLayout {
        id: content
        anchors.fill: parent; anchors.margins: 24; spacing: 16
        Label {
            text: qsTr("Prepare required files")
            color: setup.theme.ink; font.pixelSize: 22; font.weight: Font.DemiBold
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Label {
            text: setup.installer.willResume
                ? qsTr("Downloaded once and reused. Your requested task continues when setup finishes. Cancelling will keep it stopped.")
                : qsTr("After installation, start your task again.")
            color: setup.theme.muted; font.pixelSize: 14
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        ModelInstall {
            objectName: "requiredComponentInstall"
            feature: setup.installer.setupKey
            showLogAction: false
        }
        Item { Layout.fillHeight: true }
        RowLayout {
            Layout.fillWidth: true
            ActionButton {
                objectName: "showSetupLog"; text: qsTr("Progress log")
                onClicked: setup.installer.showLog()
            }
            Item { Layout.fillWidth: true }
            ActionButton {
                objectName: "closeRuntimeSetup"; text: qsTr("Close")
                onClicked: setup.close()
            }
        }
    }
}
