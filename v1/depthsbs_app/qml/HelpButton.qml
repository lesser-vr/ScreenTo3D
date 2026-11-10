import QtQuick
import QtQuick.Controls
import QtQuick.Window

Button {
    id: help
    readonly property Theme theme: Theme {}
    property string helpText: ""
    implicitWidth: 28; implicitHeight: 28
    hoverEnabled: true
    Accessible.name: qsTr("Help")
    Accessible.description: helpText
    background: Rectangle {
        anchors.centerIn: parent; width: 18; height: 18; radius: 9
        color: help.hovered || help.activeFocus ? help.theme.selection : help.theme.surface
        border.color: help.activeFocus ? help.theme.blue : help.theme.muted
    }
    contentItem: Text {
        text: "?"; color: help.theme.ink; font.pixelSize: 13; font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
    }
    ToolTip {
        objectName: "helpPopup"
        parent: help
        x: (help.width - width) / 2; y: help.height + 6
        visible: help.hovered || help.activeFocus
        delay: 300; timeout: -1; popupType: Popup.Item
        width: Math.min(340, help.Window.window ? help.Window.window.width - 24 : 340)
        margins: 12; padding: 12
        contentItem: Text {
            text: help.helpText; textFormat: Text.PlainText; wrapMode: Text.Wrap
            color: help.theme.ink; font.family: help.theme.family; font.pixelSize: 13
        }
        background: Rectangle { color: help.theme.surface; border.color: help.theme.border; radius: 8 }
    }
}
