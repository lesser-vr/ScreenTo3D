import QtQuick
import QtQuick.Controls

Item {
    id: notice
    readonly property Theme theme: Theme {}
    objectName: "vfgNotice"
    property string stereoLayout: "full-sbs"
    property string message: ""
    property bool pending: false
    readonly property bool topBottom: stereoLayout.endsWith("tb")
    readonly property int holdDuration: 1500
    readonly property int fadeDuration: 250
    opacity: 0
    visible: opacity > 0

    function show(text, preparing) {
        hold.stop()
        fade.stop()
        message = text
        pending = preparing
        opacity = text.length > 0 ? 1 : 0
        if (text.length > 0 && !preparing) hold.start()
    }

    Timer { id: hold; interval: notice.holdDuration; onTriggered: fade.start() }
    NumberAnimation {
        id: fade; target: notice; property: "opacity"; to: 0
        duration: notice.fadeDuration; easing.type: Easing.OutCubic
        onFinished: notice.message = ""
    }
    Repeater {
        model: 2
        Item {
            required property int index
            width: notice.topBottom ? notice.width : notice.width / 2
            height: notice.topBottom ? notice.height / 2 : notice.height
            x: notice.topBottom ? 0 : index * width
            y: notice.topBottom ? index * height : 0
            Item {
                id: canvas
                readonly property real scaleX: notice.stereoLayout === "half-tb" ? 2 : 1
                readonly property real scaleY: notice.stereoLayout === "half-sbs" ? 2 : 1
                width: parent.width / scaleX
                height: parent.height / scaleY
                transform: Scale { xScale: canvas.scaleX; yScale: canvas.scaleY }
                Label {
                    objectName: "vfgNoticeLabel"
                    anchors.centerIn: parent
                    width: Math.min(implicitWidth, Math.max(0, parent.width - 24))
                    text: notice.message
                    font.family: notice.theme.family; font.pixelSize: 14; font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                    leftPadding: 20; rightPadding: 20; topPadding: 12; bottomPadding: 12
                    color: "#ffffff"
                    background: Rectangle { color: "#ed15181c"; radius: 8 }
                    Accessible.role: Accessible.StaticText
                    Accessible.name: notice.message
                }
            }
        }
    }
}
