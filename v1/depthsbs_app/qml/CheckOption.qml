import QtQuick
import QtQuick.Controls.Basic

CheckBox {
    id: control
    readonly property Theme theme: Theme {}
    spacing: 8
    indicator: Rectangle {
        implicitWidth: 18; implicitHeight: 18; radius: 4
        x: control.leftPadding; y: (control.height - height) / 2
        color: control.checked ? (control.enabled ? control.theme.blue : control.theme.disabledInk) : control.theme.surface
        border.color: control.checked || control.activeFocus ? control.theme.blue : control.theme.border
        border.width: control.activeFocus ? 2 : 1
        Rectangle {
            anchors.fill: parent; anchors.margins: -3; radius: 7
            color: "transparent"; border.color: control.theme.blue; border.width: 1
            visible: control.activeFocus
        }
        Canvas {
            anchors.fill: parent; visible: control.checked
            onPaint: {
                const ctx = getContext("2d"); ctx.clearRect(0, 0, width, height)
                ctx.strokeStyle = "white"; ctx.lineWidth = 1.8; ctx.lineCap = "round"; ctx.lineJoin = "round"
                ctx.beginPath(); ctx.moveTo(4, 9); ctx.lineTo(7.5, 12.5); ctx.lineTo(14, 5.5); ctx.stroke()
            }
        }
    }
    contentItem: Text {
        text: control.text; font: control.font; color: control.enabled ? control.theme.ink : control.theme.muted
        leftPadding: control.indicator.width + control.spacing
        verticalAlignment: Text.AlignVCenter
    }
}
