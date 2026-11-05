import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Item {
    id: page
    readonly property Theme theme: Theme {}
    component MenuEntry: MenuItem {
        id: entry
        implicitWidth: 208
        implicitHeight: 36
        background: Rectangle { radius: 6; color: entry.highlighted ? page.theme.selection : "transparent" }
        contentItem: Text { text: entry.text; font: entry.font; color: entry.enabled ? page.theme.ink : page.theme.disabledInk; verticalAlignment: Text.AlignVCenter; leftPadding: 8 }
    }
    Component.onCompleted: live.setPreviewVisible(false)
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 24; spacing: 14
        RowLayout {
            Label { text: "DepthSBS"; color: page.theme.ink; font.pixelSize: 18; font.weight: Font.DemiBold; Layout.fillWidth: true }
            ToolButton {
                id: menuButton
                objectName: "mainMenuButton"; text: "메뉴"; Accessible.name: "메뉴"; implicitWidth: 32; implicitHeight: 30
                background: Rectangle { radius: 7; color: menuButton.down || menuButton.hovered ? page.theme.hover : "transparent"; border.color: menuButton.activeFocus ? page.theme.blue : "transparent" }
                contentItem: Canvas {
                    implicitWidth: 20; implicitHeight: 20
                    onPaint: {
                        const ctx = getContext("2d"); ctx.clearRect(0, 0, width, height); ctx.fillStyle = page.theme.muted
                        for (let offset of [-6, 0, 6]) { ctx.beginPath(); ctx.arc(width/2 + offset, height/2, 1.5, 0, Math.PI*2); ctx.fill() }
                    }
                }
                ToolTip.visible: hovered || activeFocus; ToolTip.text: "메뉴"; ToolTip.delay: 500
                onClicked: mainMenu.popup()
                Menu {
                    id: mainMenu
                    implicitWidth: 220
                    padding: 6
                    background: Rectangle { radius: 10; color: page.theme.surface; border.color: page.theme.border }
                    MenuEntry { objectName: "openLiveOptions"; text: "화질과 입체감"; onTriggered: page.Window.window.openPage(3) }
                    MenuEntry { text: live.sourceKind === "window" ? "모니터 전체 선택" : "창 선택으로 전환"; enabled: !live.active; onTriggered: live.setKind(live.sourceKind === "window" ? "monitor" : "window") }
                    MenuSeparator {}
                    MenuEntry { objectName: "openFiles"; text: "파일 변환"; onTriggered: page.Window.window.openPage(1) }
                    MenuEntry { objectName: "openSettings"; text: "설정과 진단"; onTriggered: page.Window.window.openPage(2) }
                }
            }
        }
        ChoicePicker {
            id: sourcePicker; objectName: "captureSource"
            implicitHeight: 72
            enabled: !live.active; model: live.sources; textRole: "label"
            currentIndex: live.selectedIndex
            displayText: currentIndex < 0 ? (count ? "대상을 선택하세요" : "선택할 대상이 없습니다") : currentText
            onActivated: live.select(currentIndex)
            Accessible.name: live.sourceKind === "window" ? "볼 창" : "볼 모니터"
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
                        Text { text: live.sourceKind === "window" ? "볼 창" : "볼 모니터"; font.pixelSize: 11; color: page.theme.muted }
                        Text { id: sourceTitle; text: sourcePicker.displayText; font.pixelSize: 14; font.weight: Font.Medium; color: page.theme.ink; elide: Text.ElideRight; Layout.fillWidth: true }
                    }
                }
            }
            Connections { target: sourcePicker.popup; function onAboutToShow() { live.refresh() } }
        }
        Item { Layout.fillHeight: true; Layout.minimumHeight: 0 }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            Rectangle { width: 6; height: 6; radius: 3; color: live.active && !live.stoppingNow ? page.theme.blue : page.theme.muted; Layout.alignment: Qt.AlignVCenter }
            Label {
            objectName: "captureStatus"; Layout.fillWidth: true
            color: page.theme.muted; wrapMode: Text.WordWrap; font.pixelSize: 12
            maximumLineCount: 2; elide: Text.ElideRight
            text: live.stoppingNow ? "SBS 종료 중…" : live.active ? (live.hasFrame ? "SBS 실행 중" : "SBS 화면 준비 중…") : desktop.busy ? "다른 작업이 끝나면 시작할 수 있습니다" : live.status
            Accessible.role: Accessible.StaticText
            }
        }
        ActionButton {
            objectName: "captureStart"; Layout.fillWidth: true; primary: true
            symbol: live.active ? "stop" : "play"
            text: live.stoppingNow ? "종료 중…" : live.active ? (live.hasFrame ? "SBS 중지" : "취소") : "SBS 시작"
            enabled: live.active ? !live.stoppingNow : !desktop.busy && live.selectedIndex >= 0
            onClicked: live.active ? live.stop() : live.startMinimal()
        }
    }
}
