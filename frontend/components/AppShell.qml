import QtQuick
import "../state" as S
import "../style" as T
import "../shared_pages/components" as C

Item {
    id: root
    objectName: "appShell"
    property string route: "home"
    property string requestedRoute: "driving"
    property string pendingCommand: ""
    property string pendingProfile: ""
    property bool recoveryOpened: false
    property bool waitingForDashboard: false

    readonly property var confirmations: ({
        reset_a: ["Reset Trip A?", "The Trip A distance will be cleared.", "RESET", true],
        reset_b: ["Reset Trip B?", "The Trip B distance and average will be cleared.", "RESET", true],
        reset_maintenance: ["Confirm the service?", "The maintenance counter will restart a full interval.", "CONFIRM", false],
        end_trip: ["End the trip?", "Statistics will be saved before closing.", "END", true],
        quit: ["Quit CliOS?", "Pending writes and services will be stopped cleanly.", "QUIT", true],
        restart: ["Restart CliOS?", "The cockpit and services will be restarted.", "RESTART", true],
        reboot: ["Reboot the system?", "The Raspberry Pi will reboot cleanly.", "REBOOT", true],
        shutdown: ["Shut down the system?", "The Raspberry Pi will shut down cleanly.", "SHUT DOWN", true],
        toggle_overlayfs: ["Change SD card protection?", "The OverlayFS configuration will change and a reboot will be required.", "CHANGE", true],
        update_activate: ["Activate the update?", "CliOS will restart to load the new version.", "ACTIVATE", true],
        update_rollback: ["Roll back to the previous version?", "CliOS will restart after the rollback.", "ROLL BACK", true]
    })

    function canonicalRoute(nextRoute) {
        if (nextRoute === "map" || nextRoute === "navigation") return "map"
        if (nextRoute === "live" || nextRoute === "data") return "live"
        if (nextRoute === "menu") return "driving"
        if (nextRoute === "diagnostic") return "vehicle"
        if (nextRoute === "transmission" || nextRoute === "vehicle_maintenance") return "vehicle"
        if (nextRoute === "services" || nextRoute === "developer") return "advanced"
        if (nextRoute === "profiles" || nextRoute === "can" || nextRoute === "logs") return "advanced"
        if (nextRoute === "leds" || nextRoute === "styles" || nextRoute === "accent") return "appearance"
        if (["maintenance", "network", "updates", "storage", "power"].indexOf(nextRoute) >= 0) return "system"
        if (["driving", "appearance", "vehicle", "system", "advanced"].indexOf(nextRoute) >= 0) return nextRoute
        return "driving"
    }

    function openRoute(nextRoute) {
        if (nextRoute === "home") { route = "home"; return }
        requestedRoute = nextRoute
        route = canonicalRoute(nextRoute)
    }

    function requestCommand(command) {
        if (command.indexOf("activate_profile:") === 0) {
            pendingProfile = command.substring("activate_profile:".length)
            confirm.title = "Activate this vehicle profile?"
            confirm.message = "CliOS will restart automatically after activating profile “" + pendingProfile + "”."
            confirm.acceptText = "ACTIVATE AND RESTART"
            confirm.dangerous = false
            confirm.visible = true
            return
        }
        if (command === "resume_trip" || command === "pause_trip" || command.indexOf("set_") === 0
                || command.indexOf("wifi_") === 0 || command === "diagnostic_scan") {
            bridge.executeUiCommand(command, S.UiState.speed)
            return
        }
        const data = confirmations[command]
        if (!data) { bridge.executeUiCommand(command, S.UiState.speed); return }
        pendingCommand = command
        confirm.title = data[0]; confirm.message = data[1]; confirm.acceptText = data[2]
        confirm.dangerous = data[3]; confirm.visible = true
    }

    function applyStyle(styleId) {
        if (styleId === T.StyleManager.styleId) return
        waitingForDashboard = true
        T.StyleManager.selectStyle(styleId)
    }

    DashboardHost {
        anchors.fill: parent
        visible: root.route === "home"
        onSettingsRequested: route => root.openRoute(route)
        onCommandRequested: command => root.requestCommand(command)
        onDashboardReady: if (root.waitingForDashboard) {
            root.waitingForDashboard = false
            root.route = "home"
        }
    }

    // Loaded on demand: QtLocation and the tile cache cost nothing
    // until the map is opened.
    Loader {
        id: mapLoader
        objectName: "mapLoader"
        anchors.fill: parent
        active: root.route === "map"
        visible: active
        source: "../shared_pages/MapPage.qml"
    }
    Connections {
        target: mapLoader.item; ignoreUnknownSignals: true
        function onCockpitRequested() { root.route = "home" }
        function onSettingsRequested() { root.openRoute("driving") }
    }
    Loader {
        id: liveLoader
        objectName: "liveLoader"
        anchors.fill: parent
        active: root.route === "live"
        visible: active
        source: "../shared_pages/LiveDataPage.qml"
    }
    Connections {
        target: liveLoader.item; ignoreUnknownSignals: true
        function onCockpitRequested() { root.route = "home" }
    }
    Shortcut {
        sequence: "Ctrl+D"
        onActivated: root.route === "live" ? root.openRoute("home") : root.openRoute("live")
    }
    Shortcut {
        sequence: "Ctrl+M"
        onActivated: root.route === "map" ? root.openRoute("home") : root.openRoute("map")
    }

    SettingsShell {
        anchors.fill: parent
        visible: ["home", "map", "live"].indexOf(root.route) < 0
        route: root.route
        requestedRoute: root.requestedRoute
        onCockpitRequested: root.route = "home"
        onCommandRequested: command => root.requestCommand(command)
        onNavigateRequested: route => root.openRoute(route)
        onStyleRequested: styleId => root.applyStyle(styleId)
    }

    Connections {
        target: bridge; ignoreUnknownSignals: true
        function onOpenMaintenanceRequested() { root.openRoute("maintenance") }
    }

    C.ConfirmDialog {
        id: confirm
        objectName: "globalConfirmDialog"
        z: 9300
        onRejected: { visible = false; root.pendingCommand = ""; root.pendingProfile = "" }
        onAccepted: {
            visible = false
            if (root.pendingProfile) {
                const profile = root.pendingProfile
                root.pendingProfile = ""
                if (bridge.setActiveProfile(profile)) bridge.restartApplication()
                return
            }
            const command = root.pendingCommand
            root.pendingCommand = ""
            bridge.executeUiCommand(command, S.UiState.speed)
        }
    }

    C.TripRecoveryDialog {
        z: 9350
        available: S.UiState.tripResumeAvailable
        secondsRemaining: S.UiState.tripResumeSeconds
        tripSummary: S.UiState.resumableTrip
        onResumeRequested: bridge.executeUiCommand("resume_trip", S.UiState.speed)
        onNewTripRequested: bridge.executeUiCommand("new_trip", S.UiState.speed)
    }

    // Monitoring alarm shown on every screen except the live data page.
    Item {
        objectName: "liveAlarmBanner"
        z: 9200
        anchors.horizontalCenter: parent.horizontalCenter
        width: alarmBanner.width; height: alarmBanner.y + alarmBanner.height
        visible: alarmBanner.shown
        C.AlertBanner {
            id: alarmBanner
            level: "danger"
            shown: S.UiState.liveAlarms.length > 0 && root.route !== "live"
            message: S.UiState.liveAlarms.length > 0
                     ? "⚠ " + S.UiState.liveAlarms[0].text + (S.UiState.liveAlarms.length > 1 ? "  (+" + (S.UiState.liveAlarms.length - 1) + ")" : "")
                     : ""
        }
        MouseArea { anchors.fill: parent; onClicked: root.openRoute("live") }
    }

    NotificationCenter { z: 9400 }
    Timer {
        interval: 500; running: !root.recoveryOpened; repeat: true
        onTriggered: if (S.UiState.recoveryMode) {
            root.recoveryOpened = true
            root.openRoute("advanced")
        }
    }
}
