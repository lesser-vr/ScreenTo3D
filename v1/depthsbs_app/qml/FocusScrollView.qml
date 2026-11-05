import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Window

ScrollView {
    id: control
    clip: true
    contentWidth: availableWidth
    function revealFocus() {
        const item = control.Window.window ? control.Window.window.activeFocusItem : null
        const flick = control.contentItem
        if (!item || !flick || !flick.contentItem)
            return
        let ancestor = item
        while (ancestor && ancestor !== flick.contentItem)
            ancestor = ancestor.parent
        if (!ancestor)
            return
        const top = item.mapToItem(flick.contentItem, 0, 0).y
        const bottom = top + item.height
        let offset = flick.contentY
        if (top < offset + 8)
            offset = top - 8
        else if (bottom > offset + flick.height - 8)
            offset = bottom - flick.height + 8
        flick.contentY = Math.max(0, Math.min(offset, flick.contentHeight - flick.height))
    }
    Connections {
        target: control.Window.window
        function onActiveFocusItemChanged() { Qt.callLater(control.revealFocus) }
    }
    onHeightChanged: Qt.callLater(revealFocus)
}
