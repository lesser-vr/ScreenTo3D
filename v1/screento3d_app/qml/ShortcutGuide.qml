pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Popup {
    id: root
    readonly property Theme theme: Theme {}
    required property var groups
    property Item returnFocusItem: null
    signal actionRequested(string action)
    objectName: "shortcutGuide"
    function showFor(item) { returnFocusItem = item; open() }
    width: Math.min(380, parent ? parent.width - 24 : 380)
    implicitHeight: headerRow.implicitHeight + guideColumn.implicitHeight + 12 + topPadding + bottomPadding
    height: Math.min(implicitHeight, parent ? Math.max(120, parent.height - 24) : implicitHeight)
    x: parent ? Math.max(12, parent.width - width - 12) : 12
    y: 12
    padding: 16
    modal: false; focus: true; popupType: Popup.Item
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    onOpened: { scroll.contentItem.contentY = 0; scroll.forceActiveFocus() }
    onClosed: if (returnFocusItem && returnFocusItem.visible && returnFocusItem.enabled) returnFocusItem.forceActiveFocus(Qt.PopupFocusReason)
    background: Rectangle { color: root.theme.surface; border.color: root.theme.border; radius: 10 }
    contentItem: ColumnLayout {
        spacing: 12
        RowLayout {
            id: headerRow; objectName: "shortcutGuideHeader"
            Layout.fillWidth: true
            Label { text: qsTr("Controls and shortcuts"); color: root.theme.ink; font.pixelSize: 17; font.weight: Font.DemiBold; Layout.fillWidth: true; wrapMode: Text.Wrap }
            ToolButton { id: closeGuide; objectName: "closeShortcutGuide"; text: qsTr("Close"); Accessible.name: qsTr("Close controls guide"); onClicked: root.close() }
        }
        ScrollView {
            id: scroll
            objectName: "shortcutGuideScroll"
            focus: true; clip: true; contentWidth: availableWidth
            rightPadding: ScrollBar.vertical.visible ? 14 : 0
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
            Keys.onEscapePressed: root.close()
            ScrollBar.vertical.policy: scroll.contentHeight > scroll.availableHeight ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
            ColumnLayout {
                id: guideColumn
                width: scroll.availableWidth; spacing: 12
                Repeater {
                    model: root.groups
                    ColumnLayout {
                        id: section
                        required property var modelData
                        Layout.fillWidth: true; spacing: 8
                        Label { text: section.modelData.title; color: root.theme.muted; font.pixelSize: 12; font.weight: Font.DemiBold; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        Repeater {
                            model: section.modelData.rows
                            ColumnLayout {
                                id: entry
                                required property var modelData
                                Layout.fillWidth: true; spacing: 5
                                RowLayout {
                                    Layout.fillWidth: true; spacing: 8
                                    Label { text: entry.modelData.label; color: root.theme.ink; font.pixelSize: 13; wrapMode: Text.Wrap; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 0 }
                                    Label {
                                        text: entry.modelData.keys; color: root.theme.ink; font.pixelSize: 12
                                        leftPadding: 6; rightPadding: 6; topPadding: 4; bottomPadding: 4
                                        background: Rectangle { color: root.theme.window; radius: 4; border.color: root.theme.border }
                                    }
                                }
                                Label { visible: entry.modelData.conflict; text: entry.modelData.status; color: root.theme.ink; wrapMode: Text.Wrap; font.pixelSize: 12; Layout.fillWidth: true }
                                Label { visible: entry.modelData.detail.length > 0; text: entry.modelData.detail; color: root.theme.muted; wrapMode: Text.Wrap; font.pixelSize: 12; Layout.fillWidth: true }
                                ActionButton { objectName: "shortcutFallback_" + entry.modelData.action; visible: entry.modelData.conflict && entry.modelData.action.length > 0; enabled: entry.modelData.enabled; text: entry.modelData.actionLabel; implicitHeight: 32; onClicked: root.actionRequested(entry.modelData.action) }
                            }
                        }
                    }
                }
                Label {
                    text: qsTr("Use the original window for keyboard and mouse input. Click the 3D title bar, then press F11 to enter fullscreen and return to the original window.")
                    color: root.theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true
                }
                Label { text: qsTr("Shortcut buttons are also available in Live output settings."); color: root.theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
            }
        }
    }
}
