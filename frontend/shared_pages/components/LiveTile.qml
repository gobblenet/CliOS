import QtQuick
import "../../style" as T
import "../../state" as S
import "../../state/SignalCatalog.js" as Catalog

// Monitoring tile: value, unit, min/max, 60 s trend and alarm.
Rectangle {
    id: root
    property var tile: ({})
    property bool editing: false
    signal removeRequested()
    signal moveRequested(int delta)
    signal editRequested()

    readonly property var info: S.UiState.signalInfo(tile.domain, tile.key)
    readonly property real numeric: Catalog.numeric(info.value)
    readonly property string level: info.stale ? "stale" : Catalog.level(tile, info.value)
    readonly property color levelColor: level === "alarm" ? T.StyleManager.danger
                                      : level === "warning" ? T.StyleManager.warning
                                      : level === "stale" ? T.StyleManager.textSecondary
                                      : T.StyleManager.accent
    property var history: []
    property real minSeen: NaN
    property real maxSeen: NaN

    function resetStats() { history = []; minSeen = NaN; maxSeen = NaN; spark.requestPaint() }
    onTileChanged: resetStats()

    radius: T.StyleManager.radiusMedium
    color: level === "alarm" ? Qt.rgba(T.StyleManager.danger.r, T.StyleManager.danger.g, T.StyleManager.danger.b, 0.16) : T.StyleManager.surface
    border.width: level === "alarm" ? 3 : T.StyleManager.borderWidth
    border.color: level === "alarm" || level === "warning" ? levelColor : T.StyleManager.outline

    SequentialAnimation on opacity {
        running: root.level === "alarm"
        loops: Animation.Infinite
        alwaysRunToEnd: true
        NumberAnimation { to: 0.6; duration: 450 }
        NumberAnimation { to: 1.0; duration: 450 }
    }

    Timer {
        interval: 500; running: true; repeat: true
        onTriggered: {
            if (root.info.stale || isNaN(root.numeric)) return
            const next = root.history.slice(-119)
            next.push(root.numeric)
            root.history = next
            root.minSeen = isNaN(root.minSeen) ? root.numeric : Math.min(root.minSeen, root.numeric)
            root.maxSeen = isNaN(root.maxSeen) ? root.numeric : Math.max(root.maxSeen, root.numeric)
            spark.requestPaint()
        }
    }

    Canvas {
        id: spark
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 12
        height: parent.height * 0.32
        opacity: 0.8
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const data = root.history
            if (data.length < 2) return
            let low = Math.min.apply(null, data), high = Math.max.apply(null, data)
            if (high - low < 1e-6) { high += 1; low -= 1 }
            ctx.strokeStyle = root.levelColor
            ctx.lineWidth = 2.5
            ctx.beginPath()
            for (let i = 0; i < data.length; i++) {
                const x = i / 119 * width
                const y = height - (data[i] - low) / (high - low) * (height - 4) - 2
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
            }
            ctx.stroke()
        }
    }

    Text {
        id: title
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.margins: 14
        text: root.info.label.toUpperCase()
        color: T.StyleManager.textSecondary
        font.pixelSize: 15; font.bold: true; font.letterSpacing: 1.1
        elide: Text.ElideRight
    }
    Row {
        anchors.left: parent.left; anchors.leftMargin: 14
        anchors.top: title.bottom; anchors.topMargin: 2
        spacing: 8
        Text {
            id: valueText
            text: root.info.present ? Catalog.format(root.info.value, root.tile.decimals) : "—"
            color: root.level === "stale" ? T.StyleManager.textSecondary : (root.level === "normal" ? T.StyleManager.text : root.levelColor)
            font.pixelSize: 52; font.bold: true
        }
        Text {
            anchors.baseline: valueText.baseline
            text: root.info.unit
            color: T.StyleManager.textSecondary
            font.pixelSize: 18
        }
    }
    Text {
        anchors.right: parent.right; anchors.top: title.bottom; anchors.rightMargin: 14; anchors.topMargin: 6
        horizontalAlignment: Text.AlignRight
        visible: !root.editing
        text: root.level === "stale" ? (root.info.present ? "STALE" : "NO DATA")
              : (isNaN(root.minSeen) ? "" : "max " + Catalog.format(root.maxSeen) + "\nmin " + Catalog.format(root.minSeen))
        color: T.StyleManager.textSecondary
        font.pixelSize: 13; font.family: T.StyleManager.fontMono
    }

    MouseArea { anchors.fill: parent; enabled: !root.editing; onPressAndHold: root.editRequested(); onDoubleClicked: root.resetStats() }

    Row {
        visible: root.editing
        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 8
        spacing: 6
        Repeater {
            model: [ { glyph: "◀", action: "left" }, { glyph: "▶", action: "right" }, { glyph: "✎", action: "edit" }, { glyph: "✕", action: "remove" } ]
            Rectangle {
                width: 44; height: 44; radius: T.StyleManager.radiusSmall
                color: modelData.action === "remove" ? Qt.darker(T.StyleManager.danger, 1.6) : T.StyleManager.surfaceRaised
                border.width: 1; border.color: T.StyleManager.outline
                Text { anchors.centerIn: parent; text: modelData.glyph; color: T.StyleManager.text; font.pixelSize: 20 }
                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        if (modelData.action === "left") root.moveRequested(-1)
                        else if (modelData.action === "right") root.moveRequested(1)
                        else if (modelData.action === "edit") root.editRequested()
                        else root.removeRequested()
                    }
                }
            }
        }
    }
}
