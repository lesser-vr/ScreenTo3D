import QtQuick

ChoicePicker {
    readonly property var keys: ["full-sbs", "half-sbs", "full-tb", "half-tb"]
    model: ["Full SBS", "Half SBS", "Full Top-and-Bottom", "Half Top-and-Bottom"]
    Accessible.name: qsTr("Stereo layout")
}
