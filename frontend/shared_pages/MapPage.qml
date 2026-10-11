import QtQuick
import QtLocation
import QtPositioning
import "components"
import "../style" as T
import "../state" as S

// Carte plein écran : position GPS, cap, trace et suivi automatique.
Item {
    id: root
    objectName: "mapPage"
    signal cockpitRequested()
    signal settingsRequested()

    property bool followVehicle: true
    property bool headingUp: true
    property bool autoZoom: true
    property real manualZoom: 16
    property var trail: []
    readonly property int maxTrailPoints: 600
    readonly property var vehicleCoordinate: QtPositioning.coordinate(S.UiState.latitude, S.UiState.longitude)
    readonly property bool hasFix: S.UiState.gpsFix
    property bool everHadFix: false

    function speedZoom(speedKmh) {
        if (speedKmh < 30) return 17.5
        if (speedKmh < 60) return 16.5
        if (speedKmh < 100) return 15.5
        return 14.5
    }

    function cardinal(deg) {
        const names = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
        return names[Math.round(((deg % 360) + 360) % 360 / 45) % 8]
    }

    function recordPosition() {
        if (!hasFix) return
        const point = QtPositioning.coordinate(S.UiState.latitude, S.UiState.longitude)
        const last = trail.length > 0 ? trail[trail.length - 1] : null
        // Une trace par déplacement réel (> 3 m) limite le bruit à l'arrêt.
        if (last && last.distanceTo(point) < 3) return
        const next = trail.slice(Math.max(0, trail.length - maxTrailPoints + 1))
        next.push(point)
        trail = next
    }

    onHasFixChanged: if (hasFix) everHadFix = true
    onVehicleCoordinateChanged: recordPosition()

    Rectangle { anchors.fill: parent; color: T.StyleManager.background }

    Plugin {
        id: tilePlugin
        name: "osm"
        PluginParameter { name: "osm.useragent"; value: "CliOS-navigation" }
        PluginParameter { name: "osm.mapping.providersrepository.disabled"; value: true }
        PluginParameter { name: "osm.mapping.custom.host"; value: S.UiState.mapTileUrl }
        PluginParameter { name: "osm.mapping.cache.disk.size"; value: 268435456 }
        PluginParameter { name: "osm.mapping.highdpi_tiles"; value: false }
    }

    Map {
        id: map
        objectName: "navigationMap"
        anchors.fill: parent
        plugin: tilePlugin
        copyrightsVisible: true
        zoomLevel: root.followVehicle && root.autoZoom ? root.speedZoom(S.UiState.gpsSpeed) : root.manualZoom
        bearing: root.followVehicle && root.headingUp ? S.UiState.heading : 0
        Binding on center {
            when: root.followVehicle && root.everHadFix
            value: vehicleMarker.coordinate
            restoreMode: Binding.RestoreNone
        }
        Behavior on zoomLevel { NumberAnimation { duration: 800; easing.type: Easing.InOutQuad } }
        Behavior on bearing { RotationAnimation { duration: 600; direction: RotationAnimation.Shortest } }

        Component.onCompleted: {
            for (let i = 0; i < supportedMapTypes.length; i++) {
                if (supportedMapTypes[i].style === MapType.CustomMap) {
                    activeMapType = supportedMapTypes[i]
                    break
                }
            }
        }

        MapPolyline {
            line.width: 7
            line.color: Qt.rgba(T.StyleManager.accent.r, T.StyleManager.accent.g, T.StyleManager.accent.b, 0.55)
            path: root.trail
        }

        MapCircle {
            visible: root.hasFix && S.UiState.gpsAccuracy > 0
            center: vehicleMarker.coordinate
            radius: S.UiState.gpsAccuracy
            color: Qt.rgba(T.StyleManager.info.r, T.StyleManager.info.g, T.StyleManager.info.b, 0.15)
            border.width: 1
            border.color: Qt.rgba(T.StyleManager.info.r, T.StyleManager.info.g, T.StyleManager.info.b, 0.5)
        }

        MapQuickItem {
            id: vehicleMarker
            visible: root.everHadFix
            coordinate: root.vehicleCoordinate
            anchorPoint.x: arrow.width / 2
            anchorPoint.y: arrow.height / 2
            // Interpolation entre deux fix (1 Hz sur Garmin) pour un mouvement fluide.
            Behavior on coordinate { CoordinateAnimation { duration: 950 } }
            sourceItem: Canvas {
                id: arrow
                width: 46; height: 46
                opacity: root.hasFix ? 1.0 : 0.45
                rotation: S.UiState.heading - map.bearing
                Behavior on rotation { RotationAnimation { duration: 600; direction: RotationAnimation.Shortest } }
                onPaint: {
                    const ctx = getContext("2d")
                    ctx.reset()
                    ctx.beginPath()
                    ctx.arc(23, 23, 21, 0, Math.PI * 2)
                    ctx.fillStyle = "white"
                    ctx.fill()
                    ctx.beginPath()
                    ctx.moveTo(23, 5); ctx.lineTo(37, 37); ctx.lineTo(23, 30); ctx.lineTo(9, 37)
                    ctx.closePath()
                    ctx.fillStyle = "#2A7DE1"
                    ctx.fill()
                }
            }
        }

        DragHandler {
            target: null
            onTranslationChanged: delta => {
                root.followVehicle = false
                map.pan(-delta.x, -delta.y)
            }
        }
        WheelHandler {
            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
            onWheel: event => {
                root.autoZoom = false
                root.manualZoom = Math.max(3, Math.min(19, map.zoomLevel + event.angleDelta.y / 240))
            }
        }
        PinchHandler {
            target: null
            onScaleChanged: delta => {
                root.autoZoom = false
                root.manualZoom = Math.max(3, Math.min(19, map.zoomLevel + Math.log2(delta)))
            }
        }
    }

    // ── Bandeau supérieur ────────────────────────────────────────────────────
    Row {
        anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 18
        spacing: 12
        Button { width: 190; height: 64; text: "‹ COCKPIT"; primary: true; onClicked: root.cockpitRequested() }
        Button { width: 160; height: 64; text: "RÉGLAGES"; onClicked: root.settingsRequested() }
    }

    Rectangle {
        id: hud
        objectName: "navigationHud"
        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 18
        width: 300; height: hudColumn.implicitHeight + 28
        radius: T.StyleManager.radiusMedium
        color: Qt.rgba(T.StyleManager.surface.r, T.StyleManager.surface.g, T.StyleManager.surface.b, 0.9)
        border.width: T.StyleManager.borderWidth; border.color: T.StyleManager.outline
        Column {
            id: hudColumn
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 14
            spacing: 4
            Row {
                spacing: 8
                // Vitesse CAN si disponible, sinon vitesse GPS.
                Text { id: speedValue; text: Math.round(S.UiState.speed > 0 ? S.UiState.speed : S.UiState.gpsSpeed); color: T.StyleManager.text; font.pixelSize: 54; font.bold: true }
                Text { anchors.baseline: speedValue.baseline; text: "km/h"; color: T.StyleManager.textSecondary; font.pixelSize: 18 }
            }
            Text {
                text: root.cardinal(S.UiState.heading) + "  " + Math.round(S.UiState.heading) + "°" + (S.UiState.headingValid ? "" : "  (à l'arrêt)")
                color: T.StyleManager.text; font.pixelSize: 20; font.bold: true
            }
            Text {
                text: root.hasFix
                      ? "GPS " + S.UiState.gpsMode + " · " + S.UiState.gpsSatellites + " sat" + (S.UiState.gpsAccuracy > 0 ? " · ±" + Math.round(S.UiState.gpsAccuracy) + " m" : "")
                      : "Recherche GPS… " + S.UiState.gpsSatellitesInView + " sat visibles"
                color: root.hasFix ? T.StyleManager.success : T.StyleManager.warning
                font.pixelSize: 15; font.bold: true
            }
            Text {
                visible: root.everHadFix
                text: S.UiState.latitude.toFixed(5) + ", " + S.UiState.longitude.toFixed(5) + "  ·  " + Math.round(S.UiState.altitude) + " m"
                color: T.StyleManager.textSecondary; font.family: T.StyleManager.fontMono; font.pixelSize: 13
            }
        }
    }

    // ── Commandes de carte ───────────────────────────────────────────────────
    Column {
        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 18
        spacing: 10
        Button { width: 210; height: 60; text: "+"; onClicked: { root.autoZoom = false; root.manualZoom = Math.min(19, map.zoomLevel + 1) } }
        Button { width: 210; height: 60; text: "−"; onClicked: { root.autoZoom = false; root.manualZoom = Math.max(3, map.zoomLevel - 1) } }
        Button {
            width: 210; height: 60
            text: root.headingUp ? "CAP EN HAUT" : "NORD EN HAUT"
            onClicked: root.headingUp = !root.headingUp
        }
        Button {
            objectName: "recenterButton"
            width: 210; height: 60
            primary: !root.followVehicle || !root.autoZoom
            text: "RECENTRER"
            onClicked: { root.followVehicle = true; root.autoZoom = true }
        }
    }

    Rectangle {
        visible: !root.everHadFix
        anchors.centerIn: parent
        width: 520; height: 120
        radius: T.StyleManager.radiusMedium
        color: Qt.rgba(T.StyleManager.surface.r, T.StyleManager.surface.g, T.StyleManager.surface.b, 0.92)
        border.width: 2; border.color: T.StyleManager.warning
        Column {
            anchors.centerIn: parent; spacing: 6
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "EN ATTENTE DU SIGNAL GPS"; color: T.StyleManager.text; font.pixelSize: 24; font.bold: true }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: S.UiState.gpsSource !== "" ? "Source : " + S.UiState.gpsSource : "Vérifiez le service GPS et le câblage de l'antenne"
                color: T.StyleManager.textSecondary; font.pixelSize: 15
            }
        }
    }

    Keys.onPressed: event => {
        if (event.key === Qt.Key_Plus || event.key === Qt.Key_Equal) { root.autoZoom = false; root.manualZoom = Math.min(19, map.zoomLevel + 1); event.accepted = true }
        else if (event.key === Qt.Key_Minus) { root.autoZoom = false; root.manualZoom = Math.max(3, map.zoomLevel - 1); event.accepted = true }
        else if (event.key === Qt.Key_C) { root.followVehicle = true; root.autoZoom = true; event.accepted = true }
        else if (event.key === Qt.Key_H) { root.headingUp = !root.headingUp; event.accepted = true }
        else if (event.key === Qt.Key_Escape) { root.cockpitRequested(); event.accepted = true }
    }
    Component.onCompleted: forceActiveFocus()
}
