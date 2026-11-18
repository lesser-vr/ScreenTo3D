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
    title: "ScreenTo3D"
    color: theme.window
    font.family: theme.family
    font.pixelSize: 14
    property bool fileWorkspace: false
    property size liveSize: Qt.size(420, 260)
    property size fileSize: Qt.size(860, 740)
    property int page: 0
    Connections {
        target: desktop.completionShutdown
        function onCountdownStarted() {
            root.openPage(1)
            root.showNormal(); root.raise(); root.requestActivate()
        }
    }
    function openPage(index) {
        if (page === index && index > 1) { tools.showNormal(); tools.raise(); tools.requestActivate() }
        else page = index
    }
    function fitWorkspace() {
        desktop.fitControlWindow(root, fileWorkspace ? 760 : 380, fileWorkspace ? 620 : 260, width, height)
    }
    function fitTools() {
        if (tools.visible)
            desktop.fitControlWindow(tools, page === 3 ? 460 : 760, page === 3 ? 430 : 620, tools.width, tools.height)
    }
    Connections {
        target: desktop
        function onWorkAreaChanged() { Qt.callLater(root.fitWorkspace); Qt.callLater(root.fitTools) }
    }
    onScreenChanged: Qt.callLater(fitWorkspace)
    onPageChanged: {
        if (fileWorkspace !== (page === 1)) {
            if (fileWorkspace) fileSize = Qt.size(width, height)
            else liveSize = Qt.size(width, height)
            fileWorkspace = page === 1
            desktop.fitControlWindow(root, fileWorkspace ? 760 : 380, fileWorkspace ? 620 : 260,
                fileWorkspace ? fileSize.width : liveSize.width, fileWorkspace ? fileSize.height : liveSize.height)
        }
        if (page > 1) {
            if (!desktop.protectWindow(tools)) return
            tools.showNormal(); tools.raise(); tools.requestActivate()
            desktop.fitControlWindow(tools, page === 3 ? 460 : 760, page === 3 ? 430 : 620,
                page === 3 ? 480 : 860, page === 3 ? 460 : 740)
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
    onClosing: function(close) {
        close.accepted = !livePage.dismissSourcePicker() && desktop.requestClose()
    }

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

    ShortcutGuide { id: mainShortcutGuide; groups: shortcutHelp.groups; onActionRequested: action => shortcutHelp.activate(action); objectName: "mainShortcutGuide"; parent: root.contentItem }
    LivePage { id: livePage; anchors.fill: parent; visible: root.page !== 1; onHelpRequested: opener => mainShortcutGuide.showFor(opener) }
    RuntimeSetup { mainWindow: root }
        Item {
            objectName: "filesPage"; anchors.fill: parent; visible: root.page === 1
            ColumnLayout {
                anchors.fill: parent; spacing: 8
                TaskHeader { files: true; Layout.fillWidth: true; Layout.topMargin: 16; Layout.leftMargin: 32; Layout.rightMargin: 32; onTaskSelected: index => root.openPage(index) }
                FocusScrollView {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: 16
                Item { height: 16 }
                Copy { text: qsTr("Convert a video to the selected stereo layout. Files are processed on this PC."); Layout.leftMargin: 32; Layout.rightMargin: 32 }
                Card {
                    Layout.leftMargin: 32; Layout.rightMargin: 32
                    implicitHeight: 94
                    border.color: drop.containsDrag ? root.accent : root.theme.border
                    DropArea { id: drop; enabled: !desktop.busy; anchors.fill: parent; onDropped: function(event) { if (event.hasUrls) { desktop.dropFiles(event.urls); event.acceptProposedAction() } } }
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 20
                        ColumnLayout { Layout.fillWidth: true; Label { text: qsTr("Drop videos here"); color: root.ink; font.weight: Font.DemiBold; font.pixelSize: 17 } Copy { text: qsTr("MP4 · MKV · MOV · M4V / Files convert automatically in queue order"); font.pixelSize: 12 } }
                        Action { objectName: "addFiles"; text: qsTr("Add files"); enabled: !desktop.busy; onClicked: desktop.chooseFiles() }
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
                            Accessible.name: modelData.name + " " + modelData.stateLabel
                            Keys.onReturnPressed: desktop.select(index)
                            Keys.onSpacePressed: desktop.select(index)
                            border.color: activeFocus ? root.accent : "transparent"
                            color: index === desktop.selectedIndex ? root.theme.selection : "transparent"
                            RowLayout { anchors.fill: parent; anchors.margins: 12; Label { text: modelData.name; color: root.ink; elide: Text.ElideMiddle; Layout.fillWidth: true } Label { text: modelData.stateLabel; color: root.accent; font.pixelSize: 12 } }
                            MouseArea { anchors.fill: parent; onClicked: desktop.select(index) }
                        }
                        Label { visible: fileList.count === 0; anchors.centerIn: parent; text: qsTr("Added videos appear here"); color: root.muted }
                    }
                }
                RowLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32
                    ColumnLayout {
                        Layout.fillWidth: true
                        RowLayout {
                            spacing: 6
                            Label { text: qsTr("Depth model"); color: root.muted }
                            HelpButton { objectName: "fileModelHelp"; Accessible.name: qsTr("File depth model and precision help"); helpText: desktop.depthModelHelp }
                        }
                        Picker {
                            objectName: "modePicker"; enabled: !desktop.busy
                            model: desktop.depthChoices; textRole: "label"; valueRole: "key"
                            currentIndex: desktop.depthChoices.map(function(m) { return m.mode + "/" + m.model }).indexOf(desktop.settings.mode + "/" + desktop.settings.model)
                            onActivated: { desktop.selectDepthModel(currentValue); desktop.rememberSelection() }
                            Accessible.name: qsTr("File depth model")
                        }
                    }
                    ColumnLayout { Layout.fillWidth: true; Copy { text: qsTr("Video codec") } Picker { enabled: !desktop.busy; model: [qsTr("H.264 · Broad compatibility"), qsTr("HEVC · Supports 4K / Check your player")]; currentIndex: desktop.settings.codec === "hevc" ? 1 : 0; onActivated: desktop.setOption("codec", currentIndex === 1 ? "hevc" : "h264") } }
                }
                ColumnLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32; Layout.fillWidth: true
                    Copy { text: qsTr("Stereo layout") }
                    StereoLayoutPicker { objectName: "fileStereoLayout"; enabled: !desktop.busy; currentIndex: keys.indexOf(desktop.settings.stereo_layout); onActivated: { desktop.setOption("stereo_layout", keys[currentIndex]); desktop.rememberSelection() } }
                }
                ColumnLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32; Layout.fillWidth: true; spacing: 8
                    RowLayout {
                        Label { text: qsTr("Depth strength"); color: root.ink; Layout.fillWidth: true }
                        Label { text: desktop.settings.depth_strength.toLocaleString(Qt.locale(i18n.localeName),"f",2)+"×"; color: root.muted }
                        Action { objectName: "resetFileStrength"; text: qsTr("Reset"); enabled: !desktop.busy; onClicked: desktop.setOption("depth_strength",0.5) }
                    }
                    Slider {
                        id: fileStrength; objectName: "fileStrength"; Layout.fillWidth: true
                        from: 0.25; to: 2; stepSize: 0.25; enabled: !desktop.busy
                        value: desktop.settings.depth_strength; onMoved: desktop.setOption("depth_strength",value)
                        Accessible.name: qsTr("File depth strength")
                        background: Rectangle {
                            x: fileStrength.leftPadding; y: fileStrength.topPadding+fileStrength.availableHeight/2-height/2
                            implicitWidth: 200; implicitHeight: 4; width: fileStrength.availableWidth; height: 4; radius: 2; color: root.theme.disabled
                            Rectangle { width: fileStrength.visualPosition*parent.width; height: parent.height; radius: 2; color: fileStrength.enabled ? root.accent : root.theme.disabledInk }
                        }
                        handle: Rectangle {
                            x: fileStrength.leftPadding+fileStrength.visualPosition*(fileStrength.availableWidth-width)
                            y: fileStrength.topPadding+fileStrength.availableHeight/2-height/2
                            implicitWidth: 20; implicitHeight: 20; radius: 10; color: root.theme.surface
                            border.color: fileStrength.activeFocus ? root.accent : root.theme.border; border.width: fileStrength.activeFocus ? 2 : 1
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 6
                        CheckOption {
                            objectName: "fileVfg"; Layout.fillWidth: false
                            text: qsTr("Frame interpolation (VFG 2×)"); enabled: !desktop.busy
                            checked: desktop.settings.vfg; onClicked: desktop.setOption("vfg",checked)
                        }
                        HelpButton {
                            objectName: "fileVfgHelp"; Accessible.name: qsTr("File VFG frame interpolation help")
                            helpText: qsTr("Off by default. Uses NVIDIA VFG to double the file's output FPS while preserving playback duration and audio. No interpolation crosses detected scene cuts. This uses additional GPU resources and may increase conversion time. The VFG runtime must be installed. File settings apply to the next conversion queue and are independent of live 3D.")
                        }
                        Item { Layout.fillWidth: true }
                    }
                    ModelInstall { feature: desktop.settings.vfg ? "vfg" : "" }
                }
                RowLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32
                    Label {
                        id: outputPathLabel; objectName: "fileOutputPath"
                        text: desktop.destination || qsTr("Save location is set automatically when you add a file")
                        color: root.muted; elide: Text.ElideMiddle; Layout.fillWidth: true
                        ToolTip.visible: outputPathLabel.visible && outputHover.hovered && desktop.destination.trim().length > 0
                        ToolTip.text: desktop.destination
                        HoverHandler { id: outputHover }
                    }
                    Action { text: qsTr("Save location"); enabled: !desktop.busy && desktop.selectedIndex >= 0; onClicked: desktop.chooseOutput() }
                    Action { text: qsTr("Remove"); enabled: !desktop.busy && desktop.selectedIndex >= 0; onClicked: desktop.removeSelected() }
                }
                ColumnLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32; Layout.fillWidth: true
                    ModelInstall { feature: "trt-core" }
                    ModelInstall { objectName: "fileGpuRuntimeInstall"; feature: desktop.gpuRuntimeKey }
                    ModelInstall { feature: "media-tools" }
                    ModelInstall { feature: desktop.settings.model }
                    RowLayout {
                        visible: desktop.settings.model === "ovda-small-c16"
                        CheckOption { text: qsTr("I confirm personal, non-commercial use and the license terms"); checked: desktop.settings.noncommercial; enabled: !desktop.busy; onClicked: desktop.setOption("noncommercial", checked) }
                        Action { text: qsTr("Read license"); onClicked: desktop.openLicense() }
                    }
                }
                ColumnLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32; Layout.fillWidth: true
                        Copy { text: qsTr("Stereo processing") }
                        Picker { enabled: !desktop.busy; model: [qsTr("CUDA · Default"), qsTr("CPU · Diagnostic comparison (slow)")]; currentIndex: desktop.settings.renderer === "cuda" ? 0 : 1; onActivated: desktop.setOption("renderer", currentIndex === 0 ? "cuda" : "cpu") }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 6
                            CheckOption {
                                objectName: "fileLetterboxRefinement"
                                Layout.fillWidth: false
                                text: qsTr("Uniform-background depth refinement for videos with black bars")
                                enabled: !desktop.busy; checked: desktop.settings.letterbox
                                onClicked: desktop.setOption("letterbox", checked)
                            }
                            HelpButton {
                                objectName: "fileLetterboxHelp"
                                Accessible.name: qsTr("Black-bar depth refinement help")
                                helpText: qsTr("Experimental · File conversion only · Default: off\n\nExtends the existing uniform-background depth refinement to the image inside detected black bars. The bars are preserved; the video is not cropped or stretched.\n\nApplied only when stable bar boundaries and a suitable uniform background are detected. General background refinement remains enabled when this option is off.")
                            }
                            Item { Layout.fillWidth: true }
                        }
                }
                Copy { text: desktop.details; font.pixelSize: 12; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                RowLayout {
                    Layout.fillWidth: true; Layout.leftMargin: 32; Layout.rightMargin: 32; spacing: 6
                    CheckOption {
                        objectName: "shutdownAfterConversion"; Layout.fillWidth: false
                        text: qsTr("Shut down Windows after all conversions finish")
                        enabled: !desktop.busy; checked: desktop.completionShutdown.selected
                        onClicked: desktop.completionShutdown.setSelected(checked)
                    }
                    HelpButton {
                        objectName: "shutdownHelp"; Accessible.name: qsTr("Shutdown after conversion help")
                        helpText: qsTr("Off by default and not saved. After every queued file converts successfully, a 30-second countdown lets you cancel shutdown. Errors or cancellation stop the queue and prevent shutdown. Other applications are not forcibly closed.")
                    }
                    Item { Layout.fillWidth: true }
                }
            }
                }
                ProgressBar {
                    id: conversionProgress
                    from: 0; to: 100; value: desktop.progress
                    Layout.fillWidth: true; Layout.leftMargin: 32; Layout.rightMargin: 32
                    background: Rectangle { implicitHeight: 6; radius: 3; color: root.theme.disabled }
                    contentItem: Item { implicitHeight: 6; Rectangle { width: conversionProgress.visualPosition * parent.width; height: parent.height; radius: 3; color: root.accent } }
                }
                RowLayout {
                    visible: desktop.completionShutdown.pending
                    Layout.fillWidth: true; Layout.leftMargin: 32; Layout.rightMargin: 32
                    Copy { text: desktop.completionShutdown.status; color: root.ink }
                    Action { objectName: "cancelShutdown"; text: qsTr("Cancel shutdown"); onClicked: desktop.completionShutdown.cancel() }
                }
                Copy { objectName: "jobStatus"; text: (desktop.queueStatus ? desktop.queueStatus + " · " : "") + (live.active ? qsTr("Stop live 3D to convert a file.") : desktop.status); color: root.ink; Layout.leftMargin: 32; Layout.rightMargin: 32 }
                RowLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32; Layout.bottomMargin: 20
                    Copy { text: desktop.licenseNotice; font.pixelSize: 12 }
                    Action { text: qsTr("Open video"); visible: desktop.canOpen; onClicked: desktop.openResult() }
                    Action { text: qsTr("Open folder"); visible: desktop.canOpen; onClicked: desktop.openResultFolder() }
                    Action { text: desktop.cancellingNow ? qsTr("Cleaning up…") : qsTr("Cancel"); enabled: desktop.canCancel; onClicked: desktop.cancel() }
                    Action { objectName: "convertButton"; text: qsTr("Start conversion"); primary: true; enabled: !desktop.busy && desktop.selectedIndex >= 0; onClicked: desktop.start() }
                }
            }
        }



    ApplicationWindow {
        id: tools; objectName: "toolsWindow"
        width: 860; height: 740; minimumWidth: 760; minimumHeight: 620
        visible: false; color: root.color
        onScreenChanged: Qt.callLater(root.fitTools)
        font: root.font; palette: root.palette
        title: root.page === 3 ? qsTr("ScreenTo3D · Live output settings") : qsTr("ScreenTo3D · Settings and diagnostics")
        onClosing: function(close) { close.accepted = false; root.page = 0 }
        onVisibleChanged: { if (visible) desktop.protectWindow(tools) }
        ShortcutGuide { id: settingsShortcutGuide; groups: shortcutHelp.groups; onActionRequested: action => shortcutHelp.activate(action); objectName: "settingsShortcutGuide"; parent: tools.contentItem }
        StackLayout {
            anchors.fill: parent
            currentIndex: root.page === 3 ? 1 : 0
        FocusScrollView {
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: 16
                Item { height: 16 }
                Heading { text: qsTr("Settings"); Layout.leftMargin: 32; Layout.rightMargin: 32 }
                Copy { text: qsTr("Manage the runtime and diagnostic tools. Choose a depth model in each workspace."); Layout.leftMargin: 32; Layout.rightMargin: 32 }
                ColumnLayout {
                    Layout.leftMargin: 32; Layout.rightMargin: 32; Layout.fillWidth: true; spacing: 12
                    Label { text: qsTr("Language"); color: root.ink }
                    Picker {
                        objectName: "languagePicker"
                        model: i18n.choices; textRole: "label"; valueRole: "key"
                        currentIndex: i18n.choices.map(function(choice) { return choice.key }).indexOf(i18n.selected)
                        onActivated: i18n.setLanguage(currentValue)
                        Accessible.name: qsTr("Language")
                    }
                    Label { text: qsTr("Data storage"); color: root.ink; font.weight: Font.DemiBold }
                    Copy { objectName: "dataPath"; text: desktop.dataPath; font.pixelSize: 12 }
                    RowLayout {
                        Action { objectName: "openDataFolder"; text: qsTr("Open data folder"); onClicked: desktop.openDataFolder() }
                    }
                    Label { text: qsTr("Check installation"); color: root.ink; font.weight: Font.DemiBold }
                    Picker { id: setupTarget; objectName: "setupTarget"; enabled: !desktop.busy; model: [qsTr("Live 3D"), qsTr("File conversion")]; Accessible.name: qsTr("Installation check target") }
                    Copy { objectName: "setupModel"; text: qsTr("Model to check · ") + (setupTarget.currentIndex === 0 ? live.liveModelLabel : desktop.models.filter(function(m) { return m.key === desktop.settings.model })[0].label); font.pixelSize: 14 }
                    RowLayout {
                        Action { objectName: "checkSetup"; text: qsTr("Check selected setup"); enabled: !desktop.busy; onClicked: desktop.checkSetupFor(setupTarget.currentIndex === 0 ? "live" : "file") }
                    }
                    Copy { objectName: "setupStatus"; text: desktop.setup; font.pixelSize: 12 }
                    Label { text: qsTr("Live 3D · Diagnostics"); color: root.ink; font.weight: Font.DemiBold }
                    Picker { objectName: "liveProcessingPath"; enabled: !live.active; model: live.nativeCapable ? [qsTr("GPU host output · Diagnostic"), qsTr("Legacy processing · Diagnostic"), qsTr("Direct GPU output · Default")] : [qsTr("GPU host output · Diagnostic"), qsTr("Legacy processing · Diagnostic")]; currentIndex: ["gpu", "reference", "gpu-texture"].indexOf(live.processingPath); onActivated: live.setProcessingPath(["gpu", "reference", "gpu-texture"][currentIndex]); Accessible.name: qsTr("Output processing path") }
                    CheckOption { id: diagnostics; text: qsTr("Show detailed status") }
                    Copy { visible: diagnostics.checked; text: live.policyDescription + "\n" + live.supportStatus + "\n" + live.metrics; font.pixelSize: 12 }
                    CheckOption { id: advanced; text: qsTr("Advanced diagnostics") }
                    ColumnLayout {
                        visible: advanced.checked; Layout.fillWidth: true
                        Action { text: qsTr("Test output display · No capture"); onClicked: pattern.show() }
                        Copy { text: qsTr("Shared runtime · Model path applies to the model selected for file conversion"); font.pixelSize: 12 }
                        Repeater {
                            model: [{key:"engine", label:qsTr("Model engine folder (DA2 Small uses its bundled location)")}, {key:"runtime", label:qsTr("TensorRT runtime")}, {key:"media", label:qsTr("Media tools")}]
                            delegate: ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                Copy { text: modelData.label; font.pixelSize: 12 }
                                RowLayout {
                                    TextField { Layout.fillWidth: true; enabled: !desktop.busy && (modelData.key !== "engine" || desktop.settings.model !== "da2-small"); text: desktop.settings[modelData.key]; selectByMouse: true; onEditingFinished: desktop.setOption(modelData.key, text) }
                                    Action { text: qsTr("Browse"); enabled: !desktop.busy && (modelData.key !== "engine" || desktop.settings.model !== "da2-small"); onClicked: desktop.chooseDirectory(modelData.key) }
                                }
                            }
                        }
                    }
                    Item { height: 24 }
                }
            }
        }
            LiveOptions {
                onShortcutHelpRequested: opener => settingsShortcutGuide.showFor(opener)
                fullscreenStats: desktop.fullscreenStats
                onFullscreenStatsRequested: enabled => desktop.setFullscreenStats(enabled)
                onDiagnosticsRequested: root.openPage(2)
            }
        }
    }

    Window {
        id: sbsOutput
        objectName: "sbsOutput"
        flags: Qt.Window | Qt.WindowDoesNotAcceptFocus
        width: 1280; height: 720; visible: false; color: "black"
        property string stats: ""
        title: "ScreenTo3D · " + live.stereoLayoutLabel + " · " + stats + " · " + shortcutHelp.fullscreenTitle
        Timer {
            interval: 1000; repeat: true; triggeredOnStart: true
            running: sbsOutput.visible && live.active
            onTriggered: sbsOutput.stats = live.outputSummary()
        }
        onClosing: function(close) { close.accepted = false; live.stop(); hide() }
        Timer { id: positionTimer; interval: 200; onTriggered: live.rememberOutput() }
        onXChanged: positionTimer.restart()
        onYChanged: positionTimer.restart()
        onWidthChanged: positionTimer.restart()
        onHeightChanged: positionTimer.restart()
        Item {
            anchors.fill: parent; focus: true
            Keys.onEscapePressed: { if (sbsOutput.visibility === Window.FullScreen) live.toggleOutputFullscreen() }
            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_F11) {
                    live.toggleOutputFullscreen()
                    event.accepted = true
                }
            }
            MouseArea {
                anchors.fill: parent; acceptedButtons: Qt.RightButton
                onClicked: outputMenu.popup()
                Menu {
                    id: outputMenu; objectName: "outputMenu"
                    onAboutToShow: live.beginOutputMenu()
                    onClosed: live.endOutputMenu()
                    MenuItem { text: sbsOutput.visibility === Window.FullScreen ? qsTr("Windowed · %1").arg(shortcutHelp.exitKey) : qsTr("Fullscreen · %1").arg(shortcutHelp.fullscreenLocalKey); onTriggered: live.toggleOutputFullscreen() }
                    MenuItem { text: qsTr("Stop 3D"); onTriggered: live.stop() }
                    MenuItem { text: qsTr("Frame interpolation (VFG) · %1").arg(shortcutHelp.vfgKey); visible: live.vfgConfigurable; checkable: true; checked: live.vfgEnabled; enabled: !live.stoppingNow && !live.vfgSwitching && (live.vfgEnabled || live.vfgUnavailableReason.length === 0); onTriggered: live.setVfg(checked) }
                    MenuItem { text: qsTr("Fullscreen performance information"); checkable: true; checked: desktop.fullscreenStats; onTriggered: desktop.setFullscreenStats(checked) }
                }
            }
            Image { objectName: "outputImage"; anchors.fill: parent; source: sbsOutput.visible && !live.nativeEnabled ? live.imageUrl : ""; fillMode: Image.PreserveAspectFit; cache: false; asynchronous: false }
            Loader {
                id: nativeOutput; anchors.fill: parent
                active: live.nativeEnabled && live.nativeReady; source: active ? "NativeFrame.qml" : ""
                Binding { target: nativeOutput.item; property: "consumer"; value: 1; when: nativeOutput.status === Loader.Ready }
                Binding { target: nativeOutput.item; property: "demand"; value: sbsOutput.visible; when: nativeOutput.status === Loader.Ready }
            }
            Image { objectName: "vfgTransitionImage"; anchors.fill: parent; source: live.transitionImageUrl; visible: live.vfgSwitching; fillMode: Image.PreserveAspectFit; cache: false; asynchronous: false }
            Label { visible: !live.hasFrame && !live.vfgSwitching; anchors.centerIn: parent; text: qsTr("ScreenTo3D · Waiting for frames"); color: "#8d98ad" }
            Item {
                id: statsRow
                readonly property bool topBottom: live.stereoLayout.endsWith("tb")
                objectName: "fullscreenStatsOverlay"
                anchors.centerIn: parent
                width: live.outputAspect > 0 ? Math.min(parent.width, parent.height * live.outputAspect) : parent.width
                height: live.outputAspect > 0 ? width / live.outputAspect : parent.height
                visible: sbsOutput.visibility === Window.FullScreen && desktop.fullscreenStats && live.hasFrame
                Repeater {
                    model: 2
                    Item {
                        required property int index
                        width: statsRow.topBottom ? statsRow.width : statsRow.width / 2
                        height: statsRow.topBottom ? statsRow.height / 2 : statsRow.height
                        x: statsRow.topBottom ? 0 : index * width
                        y: statsRow.topBottom ? index * height : 0
                        Item {
                            id: overlayCanvas
                            readonly property real scaleX: live.stereoLayout === "half-tb" ? 2 : 1
                            readonly property real scaleY: live.stereoLayout === "half-sbs" ? 2 : 1
                            width: parent.width / scaleX
                            height: parent.height / scaleY
                            transform: Scale { xScale: overlayCanvas.scaleX; yScale: overlayCanvas.scaleY }
                            Label {
                                objectName: "stereoStatsLabel"
                                anchors.top: parent.top; anchors.right: parent.right
                                anchors.topMargin: 6; anchors.rightMargin: 6
                                padding: 6; width: Math.min(implicitWidth, Math.max(0, parent.width - 12))
                                text: sbsOutput.stats; font.pixelSize: 8; wrapMode: Text.Wrap
                                horizontalAlignment: Text.AlignRight; color: "#00ff00"
                                background: Rectangle { radius: 5; color: "#bb15181c" }
                            }
                        }
                    }
                }
            }
            VfgNotice {
                id: vfgNotice
                anchors.centerIn: parent
                width: live.outputAspect > 0 ? Math.min(parent.width, parent.height * live.outputAspect) : parent.width
                height: live.outputAspect > 0 ? width / live.outputAspect : parent.height
                stereoLayout: live.stereoLayout
                Connections {
                    target: live
                    function onVfgNotification(message, pending) {
                        vfgNotice.show(sbsOutput.visible ? message : "", pending)
                    }
                }
                Connections {
                    target: sbsOutput
                    function onVisibleChanged() { if (!sbsOutput.visible) vfgNotice.show("", false) }
                }
                Connections {
                    target: i18n
                    function onChanged() {
                        if (vfgNotice.visible && vfgNotice.message.length > 0)
                            vfgNotice.message = live.vfgNoticeText
                        sbsOutput.stats = live.outputSummary()
                    }
                }
            }
        }
    }

    Window {
        id: pattern
        objectName: "patternWindow"
        width: 960; height: 540; visible: false; color: "#10141c"
        title: qsTr("ScreenTo3D · Generated test pattern (no capture)")
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
            Label { anchors.top: parent.top; anchors.horizontalCenter: parent.horizontalCenter; anchors.topMargin: 18; text: qsTr("Generated test pattern · Not captured or converted video"); color: "white" }
            Action { anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottomMargin: 18; text: qsTr("Fullscreen / Windowed · Esc to return"); onClicked: pattern.visibility === Window.FullScreen ? pattern.showNormal() : pattern.showFullScreen() }
        }
    }
}
