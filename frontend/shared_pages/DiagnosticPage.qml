import QtQuick
import QtQuick.Layouts
import "components"
import "../style" as T
import "../state" as S

Item {
    id: root
    signal backRequested()
    readonly property var codes: S.UiState.diagnosticCodes
    readonly property bool scanning: S.UiState.isScanning
    readonly property bool scanned: S.UiState.hasScanned
    readonly property bool ready: S.UiState.serviceHealth.Diag === undefined || S.UiState.serviceHealth.Diag.status !== "ERROR"
    readonly property string statusText: !ready ? "UNAVAILABLE" : scanning ? "SCANNING" : !scanned ? "READY" : codes.length ? "FAULTS" : "OK"
    readonly property color statusColor: !ready ? T.StyleManager.textSecondary : scanning ? T.StyleManager.accent : codes.length ? T.StyleManager.danger : scanned ? T.StyleManager.success : T.StyleManager.text

    ColumnLayout {
        anchors.fill: parent; anchors.margins: 16; spacing: 12
        PageHeader {
            Layout.fillWidth: true
            title: "Engine diagnostics"
            subtitle: "Reading OBD-II fault codes"
            onBackClicked: root.backRequested()
        }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 14
            Card {
            Layout.preferredWidth: 350; Layout.fillHeight: true; title: "Engine diagnostics"; highlighted: root.codes.length > 0
            ColumnLayout {
                anchors.fill: parent; spacing: 20
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    width: 180; height: 180; radius: 90
                    color: Qt.rgba(root.statusColor.r, root.statusColor.g, root.statusColor.b, 0.12)
                    border.width: 3; border.color: root.statusColor
                    Text { anchors.centerIn: parent; text: root.statusText; color: root.statusColor; font.pixelSize: 25; font.bold: true }
                }
                Text {
                    Layout.fillWidth: true
                    text: root.scanning ? "Querying the ECU" : root.codes.length ? root.codes.length + " stored code(s)" : root.scanned ? "No faults detected" : "Ready to query the ECU"
                    color: T.StyleManager.textSecondary; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                }
                Item { Layout.fillHeight: true }
                Button { Layout.fillWidth: true; text: root.scanning ? "SCAN IN PROGRESS" : "START SCAN"; primary: true; enabled: root.ready && !root.scanning; onClicked: bridge.requestDiagnosticScan() }
                Button { Layout.fillWidth: true; text: "CLEAR FAULTS"; destructive: true; enabled: false; subtext: "Backend unavailable" }
            }
        }
            Card {
                Layout.fillWidth: true; Layout.fillHeight: true; title: "DTC report"
                ListView {
                anchors.fill: parent; clip: true; spacing: 10; model: root.codes
                delegate: Rectangle {
                    width: ListView.view.width; height: 84; radius: T.StyleManager.radiusSmall
                    color: T.StyleManager.surfaceRaised; border.width: 1; border.color: T.StyleManager.danger
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 16; spacing: 20
                        Text { text: String(modelData); color: T.StyleManager.danger; font.pixelSize: 29; font.weight: Font.Bold }
                        Text { Layout.fillWidth: true; text: "Fault stored by the engine ECU"; color: T.StyleManager.textSecondary; font.pixelSize: 18 }
                    }
                }
                Text {
                    anchors.centerIn: parent; visible: root.codes.length === 0
                    text: root.scanning ? "Scanning…" : root.scanned ? "No fault codes" : "Start a scan to display DTC codes"
                    color: root.scanned ? T.StyleManager.success : T.StyleManager.textSecondary
                    font.pixelSize: 23
                }
                }
            }
        }
    }
}
