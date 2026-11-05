import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ComboBox {
    id: control
    readonly property Theme theme: Theme {}
    implicitHeight: 44
    Layout.fillWidth: true
    leftPadding: 12
    rightPadding: 36
    indicator: Canvas {
        width: 12; height: 8
        x: control.width - width - 14
        y: (control.height - height) / 2
        opacity: control.enabled ? 1 : 0.5
        onPaint: {
            const ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            ctx.strokeStyle = control.theme.muted
            ctx.lineWidth = 1.5
            ctx.beginPath(); ctx.moveTo(1, 1); ctx.lineTo(6, 6); ctx.lineTo(11, 1); ctx.stroke()
        }
    }
    background: Rectangle {
        radius: 8
        color: control.enabled ? control.theme.surface : control.theme.hover
        border.color: control.activeFocus ? control.theme.blue : control.theme.border
        border.width: control.activeFocus ? 2 : 1
    }
    contentItem: Text {
        text: control.displayText
        font: control.font
        color: control.enabled ? control.theme.ink : control.theme.muted
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    ToolTip.visible: (hovered || activeFocus) && contentItem.truncated === true
    ToolTip.text: displayText
    ToolTip.delay: 500
}
