import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Item {
    id: page
    function dismissSourcePicker() {
        if (!sourcePicker.popup.visible) return false
        sourcePicker.popup.close()
        sourcePicker.forceActiveFocus()
        return true
    }
    component KindButton: Button {
        id: kind
        required property string sourceKind
        readonly property bool selected: live.sourceKind === sourceKind
        Accessible.checkable: true; Accessible.checked: selected
        implicitHeight: 32; horizontalPadding: 14
        background: Rectangle {
            radius: 6; color: kind.selected ? page.theme.surface : "transparent"
            border.color: kind.activeFocus ? page.theme.blue : "transparent"
        }
        contentItem: Label {
            text: kind.text; color: kind.selected ? page.theme.ink : page.theme.muted
            font.weight: kind.selected ? Font.DemiBold : Font.Normal
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        }
        onClicked: live.setKind(sourceKind)
    }
    readonly property Theme theme: Theme {}
    readonly property bool installNeeded: desktop.missingModels[live.liveModel] === true || (live.vfgEnabled && desktop.missingModels.vfg)
    Component.onCompleted: live.setPreviewVisible(false)
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 24; spacing: 14
        TaskHeader {
            Layout.fillWidth: true
            onTaskSelected: index => page.Window.window.openPage(index)
            onSettingsRequested: page.Window.window.openPage(3)
        }
        ChoicePicker {
            id: sourcePicker; objectName: "captureSource"
            implicitHeight: 72
            enabled: !live.active; model: live.sources; textRole: "label"
            currentIndex: live.selectedIndex
            displayText: currentIndex < 0 ? (count ? qsTr("Select a source") : qsTr("No sources available")) : currentText
            onActivated: live.select(currentIndex)
            Accessible.name: qsTr("Window or monitor to capture")
            delegate: ItemDelegate {
                required property int index
                required property var modelData
                width: ListView.view ? ListView.view.width : sourcePicker.width
                highlighted: index === sourcePicker.highlightedIndex || index === live.selectedIndex
                contentItem: Label { text: modelData.label; color: page.theme.ink; elide: Text.ElideRight }
                background: Rectangle { radius: 5; color: parent.highlighted || parent.hovered ? page.theme.selection : page.theme.surface }
            }
            popup: Popup {
                y: sourcePicker.height
                width: sourcePicker.width
                padding: 6
                // Keep the tab strip stationary while switching between lists of different lengths.
                height: 200
                margins: 4
                background: Rectangle { radius: 10; color: page.theme.surface; border.color: page.theme.border }
                onAboutToShow: live.refresh()
                contentItem: ColumnLayout {
                    spacing: 4
                    RowLayout {
                        id: kinds
                        Rectangle {
                            radius: 8; color: page.theme.hover
                            implicitWidth: tabs.implicitWidth + 6; implicitHeight: tabs.implicitHeight + 6
                            Row {
                                id: tabs; anchors.centerIn: parent
                                KindButton { objectName: "windowInputs"; width: Math.max(48, implicitWidth); text: qsTr("Windows"); sourceKind: "window" }
                                KindButton { objectName: "monitorInputs"; text: qsTr("Entire monitor"); sourceKind: "monitor" }
                            }
                        }
                        Item { Layout.fillWidth: true }
                        ToolButton { objectName: "dismissSource"; text: qsTr("Close"); Accessible.name: qsTr("Close source picker"); onClicked: page.dismissSourcePicker() }
                    }
                    ListView {
                        id: sourceList; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        model: sourcePicker.delegateModel
                        currentIndex: sourcePicker.highlightedIndex
                        ScrollIndicator.vertical: ScrollIndicator {}
                    }
                }
            }
            contentItem: Item {
                property bool truncated: sourceTitle.truncated
                RowLayout {
                    anchors.fill: parent; spacing: 12
                    Rectangle {
                        Layout.preferredWidth: 36; Layout.preferredHeight: 36; radius: 8
                        color: page.theme.window
                        Image {
                            id: appIcon; anchors.centerIn: parent; width: 28; height: 28
                            source: live.sourceIcon; fillMode: Image.PreserveAspectFit; asynchronous: false
                        }
                        Canvas {
                            anchors.centerIn: parent; width: 24; height: 24
                            visible: appIcon.status !== Image.Ready || appIcon.sourceSize.width <= 1
                            onPaint: {
                                const ctx = getContext("2d"); ctx.clearRect(0, 0, width, height)
                                ctx.strokeStyle = page.theme.muted; ctx.lineWidth = 1.4
                                ctx.strokeRect(3, 5, 18, 14); ctx.beginPath(); ctx.moveTo(3, 9); ctx.lineTo(21, 9); ctx.stroke()
                            }
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 3
                        Text { text: live.sourceKind === "window" ? qsTr("Window or monitor to capture") : qsTr("Capture source · Entire monitor"); font.pixelSize: 11; color: page.theme.muted }
                        Text { id: sourceTitle; text: sourcePicker.displayText; font.pixelSize: 14; font.weight: Font.Medium; color: page.theme.ink; elide: Text.ElideRight; Layout.fillWidth: true }
                    }
                }
            }

        }
        Item { Layout.fillHeight: true; Layout.minimumHeight: 0 }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            Rectangle { width: 6; height: 6; radius: 3; color: live.active && !live.stoppingNow ? page.theme.blue : page.theme.muted; Layout.alignment: Qt.AlignVCenter }
            Label {
            objectName: "captureStatus"; Layout.fillWidth: true
            color: page.theme.muted; wrapMode: Text.WordWrap; font.pixelSize: 12
            maximumLineCount: 2; elide: Text.ElideRight
            text: live.vfgSwitching ? qsTr("Switching frame interpolation…") : live.stoppingNow ? qsTr("Stopping 3D…") : live.active ? (live.hasFrame ? qsTr("Live 3D is running") : qsTr("Preparing 3D output…")) : desktop.busy ? qsTr("You can start after the current task finishes") : live.status
            Accessible.role: Accessible.StaticText
            }
        }
        ActionButton {
            objectName: "captureStart"; Layout.fillWidth: true; primary: true
            symbol: live.active ? "stop" : "play"
            text: live.vfgSwitching ? qsTr("Cancel switch") : live.stoppingNow ? qsTr("Stopping…") : live.active ? (live.hasFrame ? qsTr("Stop 3D") : qsTr("Cancel")) : page.installNeeded ? qsTr("Open installation settings") : qsTr("Start 3D")
            enabled: live.vfgSwitching || (live.active ? !live.stoppingNow : !desktop.busy && (page.installNeeded || live.selectedIndex >= 0))
            onClicked: live.active ? live.stop() : page.installNeeded ? page.Window.window.openPage(3) : live.startMinimal()
        }
    }
}
