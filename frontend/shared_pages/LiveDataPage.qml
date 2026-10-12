import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QC
import "components"
import "../style" as T
import "../state" as S
import "../state/SignalCatalog.js" as Catalog

// Full-screen monitoring: any runtime signal as tiles, with alarm
// limits. The selection is saved in ui.live_tiles.
Item {
    id: root
    objectName: "liveDataPage"
    signal cockpitRequested()

    property bool editing: false
    property bool pickerOpen: false
    property int editIndex: -1
    property string filter: ""
    property var tiles: S.UiState.liveTiles

    function save(next) {
        tiles = next
        bridge.save_setting("ui.live_tiles", JSON.stringify(next))
    }
    function addTile(domain, key) {
        const next = tiles.slice()
        next.push({ domain: domain, key: key, low: null, high: null })
        save(next)
        pickerOpen = false
    }
    function removeTile(index) {
        const next = tiles.slice()
        next.splice(index, 1)
        save(next)
    }
    function moveTile(index, delta) {
        const target = index + delta
        if (target < 0 || target >= tiles.length) return
        const next = tiles.slice()
        const item = next[index]
        next[index] = next[target]
        next[target] = item
        save(next)
    }
    function setLimits(index, lowText, highText) {
        const parse = function(text) {
            const cleaned = String(text).trim().replace(",", ".")
            if (cleaned === "") return null
            const number = Number(cleaned)
            return isFinite(number) ? number : null
        }
        const next = tiles.slice()
        next[index] = Object.assign({}, next[index], { low: parse(lowText), high: parse(highText) })
        save(next)
    }
    function availableSignals() {
        const needle = filter.toLowerCase()
        return S.UiState.debugSignals.filter(function(row) {
            if (row.key.indexOf("app_cpu_") === 0) return false
            if (typeof row.value === "object" && row.value !== null) return false
            const label = Catalog.label(row.domain, row.key)
            return needle === "" || label.toLowerCase().indexOf(needle) >= 0 || (row.domain + "." + row.key).indexOf(needle) >= 0
        })
    }

    Rectangle { anchors.fill: parent; color: T.StyleManager.background }

    ColumnLayout {
        anchors.fill: parent; anchors.margins: 16; spacing: 14

        RowLayout {
            Layout.fillWidth: true; Layout.preferredHeight: 64; Layout.maximumHeight: 64; spacing: 12
            Button { Layout.preferredWidth: 190; Layout.fillHeight: true; text: "‹ COCKPIT"; primary: true; onClicked: root.cockpitRequested() }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 2
                Text { text: "VEHICLE DATA"; color: T.StyleManager.text; font.pixelSize: 24; font.bold: true; font.letterSpacing: 2 }
                Text {
                    objectName: "obdStatusText"
                    text: S.UiState.obdConnected ? "OBD-II connected · " + S.UiState.obdInterface
                                                 : "OBD-II not connected — CAN, GPS and system signals only"
                    color: S.UiState.obdConnected ? T.StyleManager.success : T.StyleManager.warning
                    font.pixelSize: 14; font.bold: true
                }
            }
            Text {
                visible: S.UiState.liveAlarms.length > 0
                text: "⚠ " + S.UiState.liveAlarms.length + " ALARM" + (S.UiState.liveAlarms.length > 1 ? "S" : "")
                color: T.StyleManager.danger; font.pixelSize: 20; font.bold: true
            }
            Button {
                Layout.preferredWidth: 220; Layout.fillHeight: true
                text: "RESET"; subtext: "Default layout"
                visible: root.editing
                onClicked: root.save(Catalog.defaultTiles)
            }
            Button {
                objectName: "liveEditButton"
                Layout.preferredWidth: 190; Layout.fillHeight: true
                text: root.editing ? "DONE" : "EDIT"; primary: root.editing
                onClicked: root.editing = !root.editing
            }
        }

        GridView {
            id: grid
            objectName: "liveTileGrid"
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true
            cellWidth: Math.floor(width / 4)
            cellHeight: Math.max(180, Math.floor(height / 3))
            model: root.tiles.length + (root.editing ? 1 : 0)
            delegate: Item {
                width: grid.cellWidth; height: grid.cellHeight
                LiveTile {
                    visible: index < root.tiles.length
                    anchors.fill: parent; anchors.margins: 7
                    tile: index < root.tiles.length ? root.tiles[index] : ({})
                    editing: root.editing
                    onRemoveRequested: root.removeTile(index)
                    onMoveRequested: delta => root.moveTile(index, delta)
                    onEditRequested: root.editIndex = index
                }
                Rectangle {
                    visible: index >= root.tiles.length
                    anchors.fill: parent; anchors.margins: 7
                    radius: T.StyleManager.radiusMedium
                    color: addTouch.pressed ? T.StyleManager.accentSoft : "transparent"
                    border.width: 2; border.color: T.StyleManager.accent
                    Text { anchors.centerIn: parent; text: "+ ADD A SIGNAL"; color: T.StyleManager.accent; font.pixelSize: 20; font.bold: true }
                    MouseArea { id: addTouch; anchors.fill: parent; onClicked: { root.filter = ""; root.pickerOpen = true } }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: root.editing ? "◀ ▶ move · ✎ alarm limits · ✕ remove"
                               : "Long press: limits · double-click: reset min/max · Ctrl+D: show/hide"
            color: T.StyleManager.textSecondary; font.pixelSize: 13
        }
    }

    // ── Signal picker ──────────────────────────────────────────────────
    Rectangle {
        objectName: "signalPicker"
        visible: root.pickerOpen
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.7)
        MouseArea { anchors.fill: parent; onClicked: root.pickerOpen = false }
        Rectangle {
            anchors.centerIn: parent
            width: 980; height: parent.height - 60
            radius: T.StyleManager.radiusMedium
            color: T.StyleManager.surface; border.width: 1; border.color: T.StyleManager.outline
            MouseArea { anchors.fill: parent }
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 18; spacing: 10
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    Text { text: "ADD A SIGNAL"; color: T.StyleManager.text; font.pixelSize: 22; font.bold: true }
                    QC.TextField {
                        id: filterField
                        Layout.fillWidth: true
                        placeholderText: "Filter (e.g. temperature, rpm, obd)…"
                        text: root.filter
                        onTextChanged: root.filter = text
                        focus: root.pickerOpen
                    }
                    Button { Layout.preferredWidth: 140; Layout.preferredHeight: 48; text: "CLOSE"; onClicked: root.pickerOpen = false }
                }
                ListView {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; spacing: 4
                    model: root.pickerOpen ? root.availableSignals() : []
                    delegate: Rectangle {
                        width: ListView.view.width; height: 54
                        radius: T.StyleManager.radiusSmall
                        color: pickTouch.pressed ? T.StyleManager.accentSoft : T.StyleManager.surfaceRaised
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; spacing: 12
                            Text { Layout.fillWidth: true; text: Catalog.label(modelData.domain, modelData.key); color: T.StyleManager.text; font.pixelSize: 18; font.bold: true; elide: Text.ElideRight }
                            Text { text: modelData.domain + "." + modelData.key; color: T.StyleManager.textSecondary; font.pixelSize: 13; font.family: T.StyleManager.fontMono }
                            Text { Layout.preferredWidth: 160; horizontalAlignment: Text.AlignRight; text: Catalog.format(modelData.value) + " " + Catalog.unit(modelData.unit); color: T.StyleManager.accent; font.pixelSize: 16 }
                        }
                        MouseArea { id: pickTouch; anchors.fill: parent; onClicked: root.addTile(modelData.domain, modelData.key) }
                    }
                }
            }
        }
    }

    // ── Alarm limits ──────────────────────────────────────────────────────
    Rectangle {
        id: limitsEditor
        objectName: "limitsEditor"
        visible: root.editIndex >= 0 && root.editIndex < root.tiles.length
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.7)
        readonly property var current: visible ? root.tiles[root.editIndex] : ({})
        onVisibleChanged: if (visible) {
            lowField.text = current.low === null || current.low === undefined ? "" : String(current.low)
            highField.text = current.high === null || current.high === undefined ? "" : String(current.high)
        }
        MouseArea { anchors.fill: parent; onClicked: root.editIndex = -1 }
        Rectangle {
            anchors.centerIn: parent
            width: 640; height: 330
            radius: T.StyleManager.radiusMedium
            color: T.StyleManager.surface; border.width: 1; border.color: T.StyleManager.outline
            MouseArea { anchors.fill: parent }
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 22; spacing: 14
                Text {
                    text: "LIMITS — " + Catalog.label(limitsEditor.current.domain, limitsEditor.current.key).toUpperCase()
                    color: T.StyleManager.text; font.pixelSize: 21; font.bold: true
                    Layout.fillWidth: true; elide: Text.ElideRight
                }
                Text { text: "Leave a field empty to disable that limit. The alarm shows on every screen."; color: T.StyleManager.textSecondary; font.pixelSize: 14; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                GridLayout {
                    columns: 2; columnSpacing: 14; rowSpacing: 10; Layout.fillWidth: true
                    Text { text: "Alarm if below"; color: T.StyleManager.text; font.pixelSize: 17 }
                    QC.TextField { id: lowField; objectName: "lowLimitField"; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                    Text { text: "Alarm if above"; color: T.StyleManager.text; font.pixelSize: 17 }
                    QC.TextField { id: highField; objectName: "highLimitField"; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                }
                Item { Layout.fillHeight: true }
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    Button { Layout.fillWidth: true; Layout.preferredHeight: 56; text: "CANCEL"; onClicked: root.editIndex = -1 }
                    Button {
                        Layout.fillWidth: true; Layout.preferredHeight: 56; text: "SAVE"; primary: true
                        onClicked: { root.setLimits(root.editIndex, lowField.text, highField.text); root.editIndex = -1 }
                    }
                }
            }
        }
    }

    Keys.onPressed: event => {
        if (event.key === Qt.Key_Escape) {
            if (root.pickerOpen) root.pickerOpen = false
            else if (root.editIndex >= 0) root.editIndex = -1
            else root.cockpitRequested()
            event.accepted = true
        }
    }
    Component.onCompleted: forceActiveFocus()
}
