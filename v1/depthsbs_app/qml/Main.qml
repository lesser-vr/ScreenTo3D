import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root
    property var liveController: live
    objectName: "mainWindow"
    width: 1180; height: 800
    minimumWidth: 980; minimumHeight: 700
    visible: true
    title: "DepthSBS"
    color: "#10141c"
    font.family: "Malgun Gothic"
    font.pixelSize: 14
    property int page: 0
    readonly property bool previewActive: root.visible && root.page === 0
    onPreviewActiveChanged: live.setPreviewVisible(previewActive)
    readonly property color ink: "#f3f4fa"
    readonly property color muted: "#aab3c6"
    readonly property color accent: "#9c91ff"
    palette.window: "#10141c"
    palette.windowText: ink
    palette.text: ink
    palette.button: "#293246"
    palette.buttonText: ink
    palette.base: "#111720"
    palette.highlight: "#7166d8"
    palette.highlightedText: "white"
    onClosing: function(close) { close.accepted = desktop.requestClose() }

    component Copy: Label {
        color: root.muted
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
        lineHeight: 1.3
    }
    component Heading: Label {
        color: root.ink; font.pixelSize: 30; font.bold: true
        Layout.fillWidth: true
    }
    component Action: Button {
        id: action
        property bool primary: false
        implicitHeight: 44
        leftPadding: 18; rightPadding: 18
        background: Rectangle {
            radius: 9
            color: !action.enabled ? "#202633" : action.down ? "#6559c5" : action.primary ? "#8275ee" : action.hovered ? "#344057" : "#273145"
            border.width: action.activeFocus ? 2 : 0
            border.color: "#cdc6ff"
        }
        contentItem: Text {
            text: action.text; font: action.font
            color: action.enabled ? "#ffffff" : "#7a8497"
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        }
    }
    component Card: Rectangle {
        color: "#191f2b"; radius: 14
        border.color: "#2a3345"
        Layout.fillWidth: true
    }
    component Picker: ComboBox {
        id: picker
        implicitHeight: 44
        Layout.fillWidth: true
        background: Rectangle { radius: 9; color: "#273145"; border.color: picker.activeFocus ? root.accent : "#364157" }
        indicator: Label { text: "⌄"; color: root.muted; anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter }
    }

    Rectangle {
        width: 216; anchors.top: parent.top; anchors.bottom: parent.bottom
        color: "#141a25"
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 20; spacing: 12
            Label { text: "◈  DepthSBS"; color: root.ink; font.pixelSize: 23; font.bold: true; Layout.topMargin: 14 }
            Label { text: "A NEW DIMENSION"; color: root.muted; font.pixelSize: 10; font.letterSpacing: 2; Layout.bottomMargin: 38 }
            Repeater {
                model: ["실시간 SBS", "파일 변환", "설정"]
                delegate: Button {
                    required property int index
                    required property string modelData
                    Layout.fillWidth: true; implicitHeight: 48
                    text: modelData
                    onClicked: root.page = index
                    background: Rectangle { radius: 10; color: root.page === index ? "#302c4e" : parent.hovered ? "#202938" : "transparent"; border.color: parent.activeFocus ? root.accent : "transparent" }
                    contentItem: Text { text: parent.text; color: root.page === index ? "#c8c0ff" : root.muted; font: parent.font; leftPadding: 16; verticalAlignment: Text.AlignVCenter }
                }
            }
            Item { Layout.fillHeight: true }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#2a3345" }
            Copy { text: live.active ? "●  화면 캡처 중" : desktop.busy ? "●  작업 실행 중" : "●  로컬 처리"; font.pixelSize: 12 }
            Copy { text: "Desktop Preview\n배포 전 개발 버전"; font.pixelSize: 11 }
        }
    }

    StackLayout {
        anchors.fill: parent; anchors.leftMargin: 216
        currentIndex: root.page

        ScrollView {
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: 18
                anchors.margins: 32
                Item { height: 16 }
                Heading { text: "화면에 깊이를 더하세요"; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                Copy { text: "화면 캡처 → 선택 모드의 깊이 모델 → Full SBS · SDR 전용 / 로컬 GPU 처리"; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                RowLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32
                    Picker { objectName: "liveMode"; enabled: !live.active; model: ["원본 미리보기", "모델별 Full SBS"]; currentIndex: live.sbsEnabled ? 1 : 0; onActivated: live.setSbs(currentIndex === 1) }
                    Picker { objectName: "livePolicy"; enabled: !live.active && live.sbsEnabled; model: live.liveModes; textRole: "label"; valueRole: "key"; currentIndex: live.liveModes.map(function(m) { return m.key }).indexOf(live.liveMode); onActivated: live.setMode(currentValue) }
                    Picker { objectName: "liveModel"; visible: live.sbsEnabled && live.liveModels.length > 1; enabled: !live.active; model: live.liveModels; textRole: "label"; valueRole: "key"; currentIndex: live.liveModels.map(function(m) { return m.key }).indexOf(live.liveModel); onActivated: live.setLiveModel(currentValue) }
                    Label { text: "입체감 " + live.depthStrength.toFixed(2) + "×"; color: root.muted }
                    Slider { objectName: "liveStrength"; enabled: !root.liveController.active && root.liveController.sbsEnabled; from: 0.25; to: 2.0; stepSize: 0.25; value: root.liveController.depthStrength; onMoved: root.liveController.setStrength(value); Layout.preferredWidth: 130 }
                }
                CheckBox { visible: live.sbsEnabled && live.liveModel === "ovda-small-c16"; enabled: !live.active; text: "oVDA 개인·비상업적 사용 및 라이선스 조건 확인"; checked: live.ovdaConfirmed; onClicked: live.setOvdaConfirmed(checked); Layout.leftMargin: 32 }
                RowLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32
                    Picker { Layout.preferredWidth: 140; Layout.fillWidth: false; enabled: !live.active; model: ["창", "모니터"]; currentIndex: live.sourceKind === "window" ? 0 : 1; onActivated: live.setKind(currentIndex === 0 ? "window" : "monitor") }
                    Picker { objectName: "captureSource"; enabled: !live.active; model: live.sources; textRole: "label"; currentIndex: live.selectedIndex; onActivated: live.select(currentIndex) }
                    Action { text: "새로고침"; enabled: !live.active; onClicked: live.refresh() }
                }
                RowLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32
                    Picker { objectName: "liveProcessingPath"; enabled: !live.active && live.sbsEnabled; model: live.nativeCapable ? ["GPU 가속 · 로컬 기본", "기존 처리 · 비교용", "GPU 직접 출력 · 실험"] : ["GPU 가속 · 모델 호스트 경계", "기존 처리 · 비교용"]; currentIndex: ["gpu", "reference", "gpu-texture"].indexOf(live.processingPath); onActivated: live.setProcessingPath(["gpu", "reference", "gpu-texture"][currentIndex]) }
                    Picker { objectName: "livePresentationHz"; enabled: !live.active; model: ["출력 목표 30 fps", "출력 목표 60 fps"]; currentIndex: live.presentationHz === 60 ? 1 : 0; onActivated: live.setPresentationHz(currentIndex === 1 ? 60 : 30) }
                }
                Card {
                    Layout.margins: 32; Layout.topMargin: 10; Layout.bottomMargin: 4
                    implicitHeight: 330
                    Image { objectName: "captureImage"; anchors.fill: parent; anchors.margins: 4; source: root.previewActive && !live.nativeEnabled ? live.imageUrl : ""; fillMode: Image.PreserveAspectFit; cache: false; asynchronous: false }
                    Loader {
                        id: nativeMain; anchors.fill: parent; anchors.margins: 4
                        active: live.nativeEnabled; source: active ? "NativeFrame.qml" : ""
                        Binding { target: nativeMain.item; property: "consumer"; value: 0; when: nativeMain.status === Loader.Ready }
                        Binding { target: nativeMain.item; property: "demand"; value: root.previewActive; when: nativeMain.status === Loader.Ready }
                    }
                    ColumnLayout {
                        visible: !live.hasFrame
                        anchors.centerIn: parent; width: parent.width - 64; spacing: 18
                        Label { text: "◈"; color: root.accent; font.pixelSize: 62; Layout.alignment: Qt.AlignHCenter }
                        Label { text: live.active ? "캡처 연결 중" : "미리 볼 화면을 선택하세요"; color: root.ink; font.pixelSize: 23; font.bold: true; Layout.alignment: Qt.AlignHCenter }
                        Copy { text: "시작하기 전에는 캡처하지 않습니다.\n화면은 녹화하거나 저장하지 않습니다."; horizontalAlignment: Text.AlignHCenter }
                    }
                }
                RowLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32
                    CheckBox { text: "커서 포함"; enabled: !live.active; checked: live.cursorIncluded; onClicked: live.setCursor(checked) }
                    Item { Layout.fillWidth: true }
                    Action { text: "정지"; enabled: live.active && !live.stoppingNow; onClicked: live.stop() }
                    Action { objectName: "captureStart"; text: live.active ? "캡처 중" : "미리보기 시작"; primary: true; enabled: !desktop.busy && live.selectedIndex >= 0; onClicked: live.start() }
                }
                Copy { objectName: "captureStatus"; text: live.status; color: root.ink; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                Copy { text: live.policyDescription; font.pixelSize: 12; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                Copy { text: live.supportStatus; font.pixelSize: 12; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                Copy { text: live.metrics; font.pixelSize: 12; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                RowLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32
                    Picker { id: outputScreen; model: live.outputScreens }
                    Action { text: "별도 출력"; onClicked: live.showOutput(outputScreen.currentIndex, false) }
                    Action { text: "전체 화면"; onClicked: live.showOutput(outputScreen.currentIndex, true) }
                }
                Copy { text: "입체감 변경은 정지 후 적용 · 전체 화면 Esc: 창 모드 · 출력은 녹화되지 않습니다."; font.pixelSize: 12; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                Item { height: 16 }
            }
        }

        ScrollView {
            objectName: "filesPage"
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: 16
                Item { height: 16 }
                Heading { text: "영상, 새로운 시선으로"; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                Copy { text: "원본 영상에서 Full SBS 영상을 만듭니다. 파일은 이 PC에서만 처리됩니다."; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                Card {
                    Layout.leftMargin: 32; Layout.rightMargin: 32
                    implicitHeight: 94
                    border.color: drop.containsDrag ? root.accent : "#3c465c"
                    DropArea { id: drop; anchors.fill: parent; onDropped: function(event) { if (event.hasUrls) { desktop.dropFiles(event.urls); event.acceptProposedAction() } } }
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 20
                        ColumnLayout { Layout.fillWidth: true; Label { text: "영상을 여기에 놓으세요"; color: root.ink; font.bold: true; font.pixelSize: 17 } Copy { text: "MP4 · MKV · MOV · M4V   /   목록 최대 32개"; font.pixelSize: 12 } }
                        Action { objectName: "addFiles"; text: "파일 추가"; onClicked: desktop.chooseFiles() }
                    }
                }
                Card {
                    Layout.leftMargin: 32; Layout.rightMargin: 32
                    implicitHeight: 146
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
                            color: index === desktop.selectedIndex ? "#2c304b" : "transparent"
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
                Copy { text: desktop.details; font.pixelSize: 12; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                ProgressBar {
                    id: conversionProgress
                    from: 0; to: 100; value: desktop.progress
                    Layout.fillWidth: true; Layout.leftMargin: 32; Layout.rightMargin: 32
                    background: Rectangle { implicitHeight: 6; radius: 3; color: "#293246" }
                    contentItem: Item { implicitHeight: 6; Rectangle { width: conversionProgress.visualPosition * parent.width; height: parent.height; radius: 3; color: root.accent } }
                }
                Copy { objectName: "jobStatus"; text: desktop.status; color: root.ink; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                RowLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32; Layout.bottomMargin: 28
                    Copy { text: desktop.licenseNotice + "\n모델 · 렌더러 변경은 설정에서"; font.pixelSize: 12 }
                    Action { text: "결과 열기"; visible: desktop.canOpen; onClicked: desktop.openResult() }
                    Action { text: desktop.cancellingNow ? "정리 중…" : "취소"; enabled: desktop.canCancel; onClicked: desktop.cancel() }
                    Action { objectName: "convertButton"; text: "선택 영상 변환"; primary: true; enabled: !desktop.busy && desktop.selectedIndex >= 0; onClicked: desktop.start() }
                }
            }
        }

        ScrollView {
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: 16
                Item { height: 16 }
                Heading { text: "내 작업에 맞게"; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                Copy { text: "모델과 실행 환경을 관리합니다. 작업 중에는 설정이 잠깁니다."; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                ColumnLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32; Layout.fillWidth: true; spacing: 12
                    Copy { text: "깊이 모델" }
                    Picker { objectName: "modelPicker"; enabled: !desktop.busy; model: desktop.models; textRole: "label"; valueRole: "key"; currentIndex: desktop.models.map(function(m) { return m.key }).indexOf(desktop.settings.model); onActivated: desktop.setOption("model", currentValue) }
                    Copy { text: desktop.licenseNotice; color: root.accent }
                    Copy { text: "모드가 깊이 모델을 지정합니다. Video Quality에서만 oVDA/VDA를 명시적으로 선택할 수 있습니다. Offline Quality는 VDA의 장면별 5프레임 앞·뒤 문맥을 사용합니다. 모델은 자동 다운로드하거나 다른 모델로 대체하지 않습니다."; font.pixelSize: 12 }
                    RowLayout {
                        visible: desktop.settings.model === "ovda-small-c16"
                        CheckBox { text: "개인·비상업적 사용 및 라이선스 조건 확인"; checked: desktop.settings.noncommercial; enabled: !desktop.busy; onClicked: desktop.setOption("noncommercial", checked) }
                        Action { text: "라이선스 읽기"; onClicked: desktop.openLicense() }
                    }
                    Copy { text: "스테레오 처리" }
                    Picker { enabled: !desktop.busy; model: ["CUDA · 검증된 로컬 GPU 경로", "CPU · 명시적 비교 경로 (느림)"]; currentIndex: desktop.settings.renderer === "cuda" ? 0 : 1; onActivated: desktop.setOption("renderer", currentIndex === 0 ? "cuda" : "cpu") }
                    CheckBox { text: "실험적 검은 여백 배경 보정 · 기존 여백 추가/제거 아님"; enabled: !desktop.busy; checked: desktop.settings.letterbox; onClicked: desktop.setOption("letterbox", checked) }
                    RowLayout {
                        Action { text: "설치 환경 확인"; enabled: !desktop.busy; onClicked: desktop.checkSetup() }
                        Action { text: "출력 화면 시험"; onClicked: pattern.show() }
                    }
                    Copy { objectName: "setupStatus"; text: desktop.setup; font.pixelSize: 12 }
                    CheckBox { id: advanced; text: "고급 설정 · 로컬 설치 경로" }
                    ColumnLayout {
                        visible: advanced.checked; Layout.fillWidth: true
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
    }

    Window {
        id: sbsOutput
        objectName: "sbsOutput"
        width: 1280; height: 720; visible: false; color: "black"
        title: "DepthSBS · Live output"
        onClosing: function(close) { close.accepted = false; hide() }
        Item {
            anchors.fill: parent; focus: true
            Keys.onEscapePressed: { if (sbsOutput.visibility === Window.FullScreen) sbsOutput.showNormal(); else sbsOutput.hide() }
            Image { objectName: "outputImage"; anchors.fill: parent; source: sbsOutput.visible && !live.nativeEnabled ? live.imageUrl : ""; fillMode: Image.PreserveAspectFit; cache: false; asynchronous: false }
            Loader {
                id: nativeOutput; anchors.fill: parent
                active: live.nativeEnabled; source: active ? "NativeFrame.qml" : ""
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
