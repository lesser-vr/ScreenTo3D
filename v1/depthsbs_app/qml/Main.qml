import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root
    readonly property Theme theme: Theme {}
    property var liveController: live
    objectName: "mainWindow"
    width: 420; height: 260
    minimumWidth: 380; minimumHeight: 260
    visible: true
    title: "DepthSBS"
    color: theme.window
    font.family: theme.family
    font.pixelSize: 14
    property int page: 0
    function openPage(index) {
        if (page === index) { tools.showNormal(); tools.raise(); tools.requestActivate() }
        else page = index
    }
    onPageChanged: {
        if (page > 0) {
            if (!desktop.protectWindow(tools)) return
            tools.minimumWidth = page === 3 ? 460 : 760
            tools.minimumHeight = page === 3 ? 430 : 620
            tools.width = page === 3 ? 480 : 860
            tools.height = page === 3 ? 460 : 740
            tools.showNormal(); tools.raise(); tools.requestActivate()
        }
        else tools.hide()
    }
    readonly property color ink: theme.ink
    readonly property color muted: theme.muted
    readonly property color accent: theme.blue
    palette.window: theme.window
    palette.windowText: ink
    palette.text: ink
    palette.button: theme.surface
    palette.buttonText: ink
    palette.base: theme.surface
    palette.highlight: theme.blue
    palette.highlightedText: "white"
    onClosing: function(close) { close.accepted = desktop.requestClose() }

    component Copy: Label {
        color: root.muted
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
        lineHeight: 1.3
    }
    component Heading: Label {
        color: root.ink; font.pixelSize: 22; font.weight: Font.DemiBold
        Layout.fillWidth: true
    }
    component Action: ActionButton {}
    component Card: Rectangle {
        color: root.theme.surface; radius: 12
        border.color: root.theme.border
        Layout.fillWidth: true
    }
    component Picker: ChoicePicker {}

    LivePage { anchors.fill: parent }

    ApplicationWindow {
        id: tools; objectName: "toolsWindow"
        width: 860; height: 740; minimumWidth: 760; minimumHeight: 620
        visible: false; color: root.color
        font: root.font; palette: root.palette
        title: root.page === 1 ? "DepthSBS · 파일 변환" : root.page === 3 ? "DepthSBS · 화질과 입체감" : "DepthSBS · 설정과 진단"
        onClosing: function(close) { close.accepted = false; root.page = 0 }
        onVisibleChanged: { if (visible) desktop.protectWindow(tools) }
        StackLayout {
            anchors.fill: parent
            currentIndex: Math.max(0, root.page - 1)
        Item {
            objectName: "filesPage"
            ColumnLayout {
                anchors.fill: parent; spacing: 8
                FocusScrollView {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: 16
                Item { height: 16 }
                Heading { text: "파일 변환"; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                Copy { text: "원본 영상에서 Full SBS 영상을 만듭니다. 파일은 이 PC에서만 처리됩니다."; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                Card {
                    Layout.leftMargin: 32; Layout.rightMargin: 32
                    implicitHeight: 94
                    border.color: drop.containsDrag ? root.accent : root.theme.border
                    DropArea { id: drop; anchors.fill: parent; onDropped: function(event) { if (event.hasUrls) { desktop.dropFiles(event.urls); event.acceptProposedAction() } } }
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 20
                        ColumnLayout { Layout.fillWidth: true; Label { text: "영상을 여기에 놓으세요"; color: root.ink; font.bold: true; font.pixelSize: 17 } Copy { text: "MP4 · MKV · MOV · M4V  /  선택한 영상 1개씩 변환"; font.pixelSize: 12 } }
                        Action { objectName: "addFiles"; text: "파일 추가"; onClicked: desktop.chooseFiles() }
                    }
                }
                Card {
                    Layout.leftMargin: 32; Layout.rightMargin: 32
                    implicitHeight: desktop.jobs.length ? 146 : 76
                    ListView {
                        id: fileList
                        anchors.fill: parent; anchors.margins: 8; clip: true
                        model: desktop.jobs; spacing: 4
                        ScrollBar.vertical: ScrollBar {}
                        delegate: Rectangle {
                            required property var modelData
                            required property int index
                            width: fileList.width; height: 54; radius: 8
                            activeFocusOnTab: true
                            Accessible.role: Accessible.ListItem
                            Accessible.name: modelData.name + " " + modelData.state
                            Keys.onReturnPressed: desktop.select(index)
                            Keys.onSpacePressed: desktop.select(index)
                            border.color: activeFocus ? root.accent : "transparent"
                            color: index === desktop.selectedIndex ? root.theme.selection : "transparent"
                            RowLayout { anchors.fill: parent; anchors.margins: 12; Label { text: modelData.name; color: root.ink; elide: Text.ElideMiddle; Layout.fillWidth: true } Label { text: modelData.state; color: root.accent; font.pixelSize: 12 } }
                            MouseArea { anchors.fill: parent; onClicked: desktop.select(index) }
                        }
                        Label { visible: fileList.count === 0; anchors.centerIn: parent; text: "추가한 영상이 여기에 표시됩니다"; color: root.muted }
                    }
                }
                RowLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32
                    ColumnLayout { Layout.fillWidth: true; Copy { text: "처리 모드" } Picker { objectName: "modePicker"; enabled: !desktop.busy; model: desktop.modes; textRole: "label"; valueRole: "key"; currentIndex: desktop.modes.map(function(m) { return m.key }).indexOf(desktop.settings.mode); onActivated: desktop.setOption("mode", currentValue) } }
                    ColumnLayout { Layout.fillWidth: true; Copy { text: "출력 형식" } Picker { enabled: !desktop.busy; model: ["H.264 · 일반 호환", "HEVC · 4K 지원 / 플레이어 확인"]; currentIndex: desktop.settings.codec === "hevc" ? 1 : 0; onActivated: desktop.setOption("codec", currentIndex === 1 ? "hevc" : "h264") } }
                }
                RowLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32
                    Label { text: desktop.destination || "저장 위치: 파일을 추가하면 자동 지정됩니다"; color: root.muted; elide: Text.ElideMiddle; Layout.fillWidth: true; ToolTip.visible: outputHover.hovered; ToolTip.text: desktop.destination; HoverHandler { id: outputHover } }
                    Action { text: "저장 위치"; enabled: !desktop.busy && desktop.selectedIndex >= 0; onClicked: desktop.chooseOutput() }
                    Action { text: "제거"; enabled: !desktop.busy && desktop.selectedIndex >= 0; onClicked: desktop.removeSelected() }
                }
                ColumnLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32; Layout.fillWidth: true
                    Copy { text: "선택한 파일 변환 모델 · " + desktop.models.filter(function(m) { return m.key === desktop.settings.model })[0].label; font.pixelSize: 12 }
                    Picker { objectName: "modelPicker"; visible: desktop.models.length > 1; enabled: !desktop.busy; model: desktop.models; textRole: "label"; valueRole: "key"; currentIndex: desktop.models.map(function(m) { return m.key }).indexOf(desktop.settings.model); onActivated: desktop.setOption("model", currentValue) }
                    Copy { text: desktop.settings.mode === "offline-quality" ? "파일 전용 · VDA의 장면별 5프레임 문맥 사용" : "모델 자동 다운로드·대체 없음"; font.pixelSize: 12 }
                    RowLayout {
                        visible: desktop.settings.model === "ovda-small-c16"
                        CheckOption { text: "개인·비상업적 사용 및 라이선스 조건 확인"; checked: desktop.settings.noncommercial; enabled: !desktop.busy; onClicked: desktop.setOption("noncommercial", checked) }
                        Action { text: "라이선스 읽기"; onClicked: desktop.openLicense() }
                    }
                }
                Copy { text: desktop.details; font.pixelSize: 12; Layout.leftMargin: 32; Layout.rightMargin: 32 }
            }
                }
                ProgressBar {
                    id: conversionProgress
                    from: 0; to: 100; value: desktop.progress
                    Layout.fillWidth: true; Layout.leftMargin: 32; Layout.rightMargin: 32
                    background: Rectangle { implicitHeight: 6; radius: 3; color: root.theme.disabled }
                    contentItem: Item { implicitHeight: 6; Rectangle { width: conversionProgress.visualPosition * parent.width; height: parent.height; radius: 3; color: root.accent } }
                }
                Copy { objectName: "jobStatus"; text: desktop.status; color: root.ink; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                RowLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32; Layout.bottomMargin: 20
                    Copy { text: desktop.licenseNotice; font.pixelSize: 12 }
                    Action { text: "영상 열기"; visible: desktop.canOpen; onClicked: desktop.openResult() }
                    Action { text: "폴더 열기"; visible: desktop.canOpen; onClicked: desktop.openResultFolder() }
                    Action { text: desktop.cancellingNow ? "정리 중…" : "취소"; enabled: desktop.canCancel; onClicked: desktop.cancel() }
                    Action { objectName: "convertButton"; text: "선택 영상 변환"; primary: true; enabled: !desktop.busy && desktop.selectedIndex >= 0; onClicked: desktop.start() }
                }
            }
        }

        FocusScrollView {
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: 16
                Item { height: 16 }
                Heading { text: "설정"; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                Copy { text: "실행 환경과 진단 도구를 관리합니다. 처리 모드는 각 작업 화면에서 선택하세요."; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                ColumnLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32; Layout.fillWidth: true; spacing: 12
                    Label { text: "설치 환경 확인"; color: root.ink; font.bold: true }
                    Picker { id: setupTarget; objectName: "setupTarget"; enabled: !desktop.busy; model: ["실시간 SBS", "파일 변환"]; Accessible.name: "설치 확인 대상" }
                    Copy { objectName: "setupModel"; text: "확인할 모델 · " + (setupTarget.currentIndex === 0 ? live.liveModelLabel : desktop.models.filter(function(m) { return m.key === desktop.settings.model })[0].label); font.pixelSize: 14 }
                    RowLayout {
                        Action { objectName: "checkSetup"; text: "선택한 환경 확인"; enabled: !desktop.busy; onClicked: desktop.checkSetupFor(setupTarget.currentIndex === 0 ? "live" : "file") }
                    }
                    Copy { objectName: "setupStatus"; text: desktop.setup; font.pixelSize: 12 }
                    Label { text: "실시간 SBS · 진단 설정"; color: root.ink; font.bold: true }
                    Copy { text: "출력 FPS 제한 · 무제한은 가능한 속도로 출력합니다"; font.pixelSize: 12 }
                    Picker { objectName: "livePresentationHz"; enabled: !live.active; model: ["무제한 · 기본", "30 FPS", "60 FPS"]; currentIndex: [0, 30, 60].indexOf(live.presentationHz); onActivated: live.setPresentationHz([0, 30, 60][currentIndex]); Accessible.name: "출력 FPS 제한" }
                    Picker { objectName: "liveProcessingPath"; enabled: !live.active; model: live.nativeCapable ? ["GPU 호스트 출력 · 진단용", "기존 처리 · 진단용", "GPU 직접 출력 · 기본"] : ["GPU 호스트 출력 · 진단용", "기존 처리 · 진단용"]; currentIndex: ["gpu", "reference", "gpu-texture"].indexOf(live.processingPath); onActivated: live.setProcessingPath(["gpu", "reference", "gpu-texture"][currentIndex]); Accessible.name: "출력 처리 경로" }
                    CheckOption { id: diagnostics; text: "상세 상태 보기" }
                    Copy { visible: diagnostics.checked; text: live.policyDescription + "\n" + live.supportStatus + "\n" + live.metrics; font.pixelSize: 12 }
                    CheckOption { id: advanced; text: "고급 설정 · 진단" }
                    ColumnLayout {
                        visible: advanced.checked; Layout.fillWidth: true
                        Copy { text: "파일 변환 전용 · 스테레오 처리" }
                        Picker { enabled: !desktop.busy; model: ["CUDA · 기본", "CPU · 비교 진단용 (느림)"]; currentIndex: desktop.settings.renderer === "cuda" ? 0 : 1; onActivated: desktop.setOption("renderer", currentIndex === 0 ? "cuda" : "cpu") }
                        CheckOption { text: "파일 변환 · 실험적 검은 여백 배경 보정"; enabled: !desktop.busy; checked: desktop.settings.letterbox; onClicked: desktop.setOption("letterbox", checked) }
                        Action { text: "출력 화면 시험 · 캡처 없음"; onClicked: pattern.show() }
                        Copy { text: "공통 실행 환경 · 모델 경로는 파일 변환에서 선택한 모델에 적용"; font.pixelSize: 12 }
                        Repeater {
                            model: [{key:"engine", label:"모델 엔진 폴더 (DA2 Small은 내장 위치)"}, {key:"runtime", label:"TensorRT 실행 환경"}, {key:"media", label:"영상 도구"}]
                            delegate: ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                Copy { text: modelData.label; font.pixelSize: 12 }
                                RowLayout {
                                    TextField { Layout.fillWidth: true; enabled: !desktop.busy && (modelData.key !== "engine" || desktop.settings.model !== "da2-small"); text: desktop.settings[modelData.key]; selectByMouse: true; onEditingFinished: desktop.setOption(modelData.key, text) }
                                    Action { text: "찾기"; enabled: !desktop.busy && (modelData.key !== "engine" || desktop.settings.model !== "da2-small"); onClicked: desktop.chooseDirectory(modelData.key) }
                                }
                            }
                        }
                    }
                    Item { height: 24 }
                }
            }
        }
            LiveOptions {}
        }
    }

    Window {
        id: sbsOutput
        objectName: "sbsOutput"
        width: 1280; height: 720; visible: false; color: "black"
        title: "DepthSBS · SBS · F11 전체 화면"
        onClosing: function(close) { close.accepted = false; live.stop(); hide() }
        Timer { id: positionTimer; interval: 200; onTriggered: live.rememberOutput() }
        onXChanged: positionTimer.restart()
        onYChanged: positionTimer.restart()
        onWidthChanged: positionTimer.restart()
        onHeightChanged: positionTimer.restart()
        Item {
            anchors.fill: parent; focus: true
            Keys.onEscapePressed: { if (sbsOutput.visibility === Window.FullScreen) sbsOutput.showNormal() }
            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_F11) {
                    live.rememberOutput()
                    sbsOutput.visibility === Window.FullScreen ? sbsOutput.showNormal() : sbsOutput.showFullScreen()
                    event.accepted = true
                }
            }
            MouseArea {
                anchors.fill: parent; acceptedButtons: Qt.RightButton
                onClicked: outputMenu.popup()
                Menu {
                    id: outputMenu
                    MenuItem { text: sbsOutput.visibility === Window.FullScreen ? "창 모드 · Esc" : "전체 화면 · F11"; onTriggered: { live.rememberOutput(); sbsOutput.visibility === Window.FullScreen ? sbsOutput.showNormal() : sbsOutput.showFullScreen() } }
                    MenuItem { text: "SBS 중지"; onTriggered: live.stop() }
                }
            }
            Image { objectName: "outputImage"; anchors.fill: parent; source: sbsOutput.visible && !live.nativeEnabled ? live.imageUrl : ""; fillMode: Image.PreserveAspectFit; cache: false; asynchronous: false }
            Loader {
                id: nativeOutput; anchors.fill: parent
                active: live.nativeEnabled && live.nativeReady; source: active ? "NativeFrame.qml" : ""
                Binding { target: nativeOutput.item; property: "consumer"; value: 1; when: nativeOutput.status === Loader.Ready }
                Binding { target: nativeOutput.item; property: "demand"; value: sbsOutput.visible; when: nativeOutput.status === Loader.Ready }
            }
            Label { visible: !live.hasFrame; anchors.centerIn: parent; text: "DepthSBS · 화면 대기 중"; color: "#8d98ad" }
        }
    }

    Window {
        id: pattern
        objectName: "patternWindow"
        width: 960; height: 540; visible: false; color: "#10141c"
        title: "DepthSBS · 생성 테스트 패턴 (캡처 아님)"
        onClosing: function(close) { close.accepted = false; hide() }
        Item {
            anchors.fill: parent; focus: true
            Keys.onEscapePressed: { if (pattern.visibility === Window.FullScreen) pattern.showNormal(); else pattern.hide() }
            Row {
                anchors.fill: parent; spacing: 2
                Repeater {
                    model: ["LEFT", "RIGHT"]
                    delegate: Rectangle {
                        required property string modelData
                        width: (pattern.width - 2) / 2; height: pattern.height
                        color: modelData === "LEFT" ? "#202441" : "#172f3c"
                        Label { anchors.centerIn: parent; text: modelData; color: "#e1dfff"; font.pixelSize: 46 }
                        Rectangle { width: 50; height: 50; radius: 12; color: "#a79cff"; y: parent.height * .64
                            SequentialAnimation on x { loops: Animation.Infinite; running: pattern.visible; NumberAnimation { from: 20; to: 360; duration: 1600 } NumberAnimation { to: 20; duration: 1600 } }
                        }
                    }
                }
            }
            Label { anchors.top: parent.top; anchors.horizontalCenter: parent.horizontalCenter; anchors.topMargin: 18; text: "생성 테스트 패턴 · 실제 캡처 / 변환 영상이 아닙니다"; color: "white" }
            Action { anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottomMargin: 18; text: "전체화면 / 창 모드 · Esc로 돌아가기"; onClicked: pattern.visibility === Window.FullScreen ? pattern.showNormal() : pattern.showFullScreen() }
        }
    }
}
