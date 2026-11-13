import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: dialog
    required property var mainWindow
    readonly property Theme theme: Theme {}
    readonly property var manager: desktop.dataManager
    objectName: "portableDataWindow"
    title: qsTr("ScreenTo3D · Portable data")
    width: 600; height: 570; minimumWidth: 430; minimumHeight: 400
    visible: manager.shown; transientParent: mainWindow; color: theme.window
    onVisibleChanged: {
        if (visible) {
            cleanup.checked = false
            if (!desktop.protectWindow(dialog)) manager.dismiss()
            else desktop.fitControlWindow(dialog,430,400,width,height)
        }
    }
    onClosing: function(close) { close.accepted = false; manager.dismiss() }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 24; spacing: 14
        Label { text: qsTr("Keep everything in this app folder"); font.pixelSize: 22; font.bold: true; color: dialog.theme.ink; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        FocusScrollView {
            Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: 12
                Label { text: qsTr("Settings, models, runtimes and caches are saved under data. Moving this app folder keeps them together."); color: dialog.theme.muted; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Label { text: qsTr("Destination"); color: dialog.theme.ink; font.bold: true }
                TextArea { text: dialog.manager.path; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: dialog.theme.ink; Layout.fillWidth: true; background: Rectangle { color: dialog.theme.surface; radius: 6 } }
                Label { text: qsTr("Previous locations · %1 GB to import").arg(Number(dialog.manager.sourceGB).toLocaleString(Qt.locale(),"f",2)); color: dialog.theme.ink; font.bold: true; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                TextArea { text: dialog.manager.sourcePaths || qsTr("No previous model files found. Saved settings can still be imported."); readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: dialog.theme.muted; Layout.fillWidth: true; background: Rectangle { color: dialog.theme.surface; radius: 6 } }
                CheckOption { id: settings; objectName: "importLegacySettings"; text: qsTr("Import previous settings once"); checked: true; enabled: !dialog.manager.active }
                CheckOption { id: cleanup; objectName: "removeImportedOriginals"; text: qsTr("Remove imported original files after verification"); checked: false; enabled: !dialog.manager.active }
                Label { text: qsTr("Only successfully copied, unchanged source files are eligible for removal. Conflicts and other files stay where they are."); color: dialog.theme.muted; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Label { text: dialog.manager.status; color: dialog.theme.ink; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                ProgressBar { visible: dialog.manager.active; from: 0; to: 100; value: dialog.manager.progress; Layout.fillWidth: true }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            ActionButton { text: qsTr("Open data folder"); onClicked: dialog.manager.openFolder() }
            Item { Layout.fillWidth: true }
            ActionButton { objectName: "closePortableData"; text: dialog.manager.active ? qsTr("Cancel") : qsTr("Close"); onClicked: dialog.manager.dismiss() }
            ActionButton { objectName: "importPortableData"; text: qsTr("Import"); primary: true; enabled: !desktop.busy; onClicked: dialog.manager.begin(settings.checked,cleanup.checked) }
        }
    }
}
