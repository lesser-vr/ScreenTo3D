import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: header
    property bool files: false
    signal taskSelected(int index)
    signal settingsRequested()
    spacing: 8
    readonly property Theme theme: Theme {}
    component Segment: TabButton {
        id: segment
        implicitHeight: 30
        background: Rectangle {
            radius: 6
            color: segment.checked ? header.theme.surface : "transparent"
            border.color: segment.activeFocus ? header.theme.blue : "transparent"
        }
        contentItem: Label {
            text: segment.text
            color: segment.checked ? header.theme.ink : header.theme.muted
            font.weight: segment.checked ? Font.DemiBold : Font.Normal
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }

    TabBar {
        implicitWidth: 200
        currentIndex: header.files ? 1 : 0
        padding: 3
        background: Rectangle { radius: 8; color: header.theme.hover }
        Segment { objectName: header.files ? "returnLive" : "liveTab"; text: qsTr("Live 3D"); onClicked: header.taskSelected(0) }
        Segment { objectName: header.files ? "filesTab" : "openFiles"; text: qsTr("File conversion"); onClicked: header.taskSelected(1) }
        // Each header belongs to one workspace. Reflect keyboard tab changes too.
        Keys.onLeftPressed: header.taskSelected(0)
        Keys.onRightPressed: header.taskSelected(1)
        onVisibleChanged: if (visible) currentIndex = header.files ? 1 : 0
    }
    Item { Layout.fillWidth: true }
    ToolButton {
        id: settings
        visible: !header.files
        objectName: header.files ? "fileOptions" : "openLiveOptions"
        implicitWidth: 40; implicitHeight: 36
        background: Rectangle {
            radius: 8; color: settings.hovered || settings.down ? header.theme.hover : "transparent"
            border.color: settings.activeFocus ? header.theme.blue : "transparent"
        }
        contentItem: Item {
            Canvas {
                anchors.centerIn: parent; width: 16; height: 16
                onPaint: {
                    const ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)
                    ctx.save()
                    ctx.scale(width / 24, height / 24)
                    ctx.strokeStyle = header.theme.ink; ctx.fillStyle = header.theme.window
                    ctx.lineWidth = 1.8; ctx.lineCap = "round"
                    for (let i = 0; i < 3; ++i) {
                        const y = 5 + i * 7
                        ctx.beginPath(); ctx.moveTo(3, y); ctx.lineTo(21, y); ctx.stroke()
                        ctx.beginPath(); ctx.arc(i === 1 ? 16 : 8, y, 2.5, 0, 2 * Math.PI); ctx.fill(); ctx.stroke()
                    }
                    ctx.restore()
                }
            }
        }
        Accessible.name: header.files ? qsTr("File conversion settings") : qsTr("Live output settings")
        ToolTip.visible: settings.visible && settings.enabled && settings.Accessible.name.trim().length > 0 && (hovered || activeFocus)
        ToolTip.text: Accessible.name
        onClicked: header.settingsRequested()
    }
}
