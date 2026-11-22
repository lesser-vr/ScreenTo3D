import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: log
    required property var mainWindow
    readonly property Theme theme: Theme {}
    readonly property var installer: desktop.modelDownloads
    objectName: "installationLogWindow"
    title: qsTr("Installation progress")
    width: 610; height: 390
    minimumWidth: 360; minimumHeight: 235
    color: theme.window
    transientParent: mainWindow
    visible: installer.logVisible
    onVisibleChanged: {
        if (visible && desktop.protectWindow(log)) {
            log.raise()
            log.requestActivate()
        } else if (visible) {
            installer.hideLog()
        }
    }
    onClosing: installer.hideLog()

    ColumnLayout {
        anchors.fill: parent; anchors.margins: 20; spacing: 12
        ScrollView {
            id: scroll
            Layout.fillWidth: true; Layout.fillHeight: true
            contentWidth: availableWidth
            TextArea {
                id: output
                objectName: "installationLogText"
                readOnly: true
                selectByMouse: true
                textFormat: TextEdit.PlainText
                wrapMode: TextEdit.Wrap
                text: { i18n.effectiveLanguage; return log.installer.logText }
                placeholderText: qsTr("Installation activity will appear here.")
                color: log.theme.ink
                selectionColor: log.theme.selection; selectedTextColor: log.theme.ink
                font.pixelSize: 14
                Accessible.name: log.title
                background: Rectangle {
                    color: log.theme.surface; border.color: log.theme.border; radius: 6
                }
                onTextChanged: {
                    if (!selectedText && scroll.contentItem && scroll.contentItem.atYEnd)
                        Qt.callLater(scroll.scrollToEnd)
                }
            }
            function scrollToEnd() {
                contentItem.contentY = Math.max(0, contentHeight - availableHeight)
            }
        }
        ActionButton {
            text: qsTr("Close"); Layout.alignment: Qt.AlignRight
            onClicked: log.close()
        }
    }
}
