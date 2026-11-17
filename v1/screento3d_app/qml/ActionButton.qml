import QtQuick
import QtQuick.Controls.Basic

Button {
    id: control
    readonly property Theme theme: Theme {}
    property bool primary: false
    property string symbol: ""
    implicitHeight: 40
    font.weight: primary ? Font.DemiBold : Font.Medium
    leftPadding: 16
    rightPadding: 16
    background: Rectangle {
        radius: 9
        color: !control.enabled ? control.theme.disabled : control.primary || control.highlighted ? (control.down ? control.theme.bluePressed : control.hovered ? control.theme.blueHover : control.theme.blue) : control.down ? control.theme.disabled : control.hovered ? control.theme.hover : control.theme.surface
        border.width: control.activeFocus ? 2 : control.primary || control.highlighted ? 0 : 1
        border.color: control.activeFocus ? control.theme.blue : control.theme.border
        Rectangle {
            anchors.fill: parent; anchors.margins: -3; radius: 12
            color: "transparent"; border.width: 1; border.color: control.theme.blue
            visible: control.activeFocus && (control.primary || control.highlighted)
        }
    }
    contentItem: Item {
        implicitWidth: label.implicitWidth + (control.symbol ? 22 : 0)
        implicitHeight: label.implicitHeight
        Row {
            anchors.centerIn: parent; spacing: 8
            Canvas {
                id: symbolCanvas
                width: 14; height: 14; anchors.verticalCenter: parent.verticalCenter
                visible: control.symbol !== ""
                property color ink: !control.enabled ? control.theme.disabledInk : control.primary || control.highlighted ? "white" : control.theme.ink
                onInkChanged: requestPaint()
                Connections { target: control; function onSymbolChanged() { symbolCanvas.requestPaint() } }
                onPaint: {
                    const ctx = getContext("2d"); ctx.clearRect(0, 0, width, height); ctx.fillStyle = ink
                    if (control.symbol === "play") { ctx.beginPath(); ctx.moveTo(3, 1); ctx.lineTo(12, 7); ctx.lineTo(3, 13); ctx.closePath(); ctx.fill() }
                    else if (control.symbol === "stop") ctx.fillRect(3, 3, 9, 9)
                }
            }
            Text {
                id: label; text: control.text; font: control.font
                color: !control.enabled ? control.theme.disabledInk : control.primary || control.highlighted ? "white" : control.theme.ink
            }
        }
    }
}
