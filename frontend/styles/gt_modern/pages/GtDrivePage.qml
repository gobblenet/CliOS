import QtQuick
import QtQuick.Layouts
import "../components"
import "../../../style" as T
import "../../../state" as S

Item {
    id: root

    GridLayout {
        anchors.fill: parent
        anchors.margins: 16
        columns: 3
        rows: 2
        columnSpacing: 14
        rowSpacing: 14

        GtCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.columnSpan: 2
            title: "CliOS GT · driving"
            highlighted: S.UiState.tripActive

            RowLayout {
                anchors.fill: parent
                spacing: 28
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Text {
                        text: S.UiState.profileName()
                        color: T.StyleManager.text
                        font.family: T.StyleManager.fontFamily
                        font.pixelSize: 34
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: S.UiState.tripActive ? "Trip in progress · recording" :
                              (S.UiState.sessionState === "PAUSED" ? "Trip paused" : "Ready to drive")
                        color: S.UiState.tripActive ? T.StyleManager.success : T.StyleManager.textSecondary
                        font.family: T.StyleManager.fontFamily
                        font.pixelSize: 19
                    }
                }
                GtMetric {
                    Layout.preferredWidth: 230
                    label: "Odometer"
                    value: S.UiState.fixed(S.UiState.odometer, 0, "0")
                    unit: "km"
                    alignment: Text.AlignRight
                }
            }
        }

        GtCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: "Consumption"
            ColumnLayout {
                anchors.fill: parent
                spacing: 12
                GtMetric {
                    Layout.fillWidth: true
                    label: "Instant"
                    value: S.UiState.fixed(S.UiState.instantCons, 1, "0,0")
                    unit: "L/100"
                }
                GtMetric {
                    Layout.fillWidth: true
                    label: "Trip average"
                    value: S.UiState.fixed(S.UiState.avgConsSession, 1, "0,0")
                    unit: "L/100"
                    valueSize: 28
                }
            }
        }

        GtCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: "Trip computer"
            RowLayout {
                anchors.fill: parent
                spacing: 28
                GtMetric { Layout.fillWidth: true; label: "Trip A"; value: S.UiState.fixed(S.UiState.tripA, 1, "0,0"); unit: "km" }
                GtMetric { Layout.fillWidth: true; label: "Trip B"; value: S.UiState.fixed(S.UiState.tripB, 1, "0,0"); unit: "km" }
                GtMetric { Layout.fillWidth: true; label: "Avg. B"; value: S.UiState.fixed(S.UiState.avgConsB, 1, "0,0"); unit: "L/100" }
            }
        }

        GtCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: "Maintenance"
            GtMetric {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width * 0.44
                label: "Service"
                value: S.UiState.fixed(S.UiState.kmBeforeService, 0, "—")
                unit: "km"
                valueColor: S.UiState.serviceWarning ? T.StyleManager.warning : T.StyleManager.text
            }
            GtProgress {
                anchors.left: parent.horizontalCenter
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                height: 12
                value: S.UiState.number(S.UiState.kmBeforeService, 0)
                to: 20000
                fillColor: S.UiState.serviceWarning ? T.StyleManager.warning : T.StyleManager.success
            }
        }

        GtCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: "Vehicle status"
            highlighted: S.UiState.attentionVehicle
            RowLayout {
                anchors.fill: parent
                spacing: 12
                Text {
                    Layout.fillWidth: true
                    text: S.UiState.attentionVehicle ? "ATTENTION NEEDED" : "VEHICLE READY"
                    color: S.UiState.attentionVehicle ? T.StyleManager.warning : T.StyleManager.success
                    font.family: T.StyleManager.fontFamily
                    font.pixelSize: S.UiState.attentionVehicle ? 20 : 22
                    font.weight: Font.Bold
                    wrapMode: Text.WordWrap
                }
                Column {
                    Layout.preferredWidth: 155
                    spacing: 5
                    Text { text: S.UiState.driverUnbelted ? "Driver seatbelt" : "Seatbelt fastened"; color: T.StyleManager.textSecondary; font.pixelSize: 17 }
                    Text { text: S.UiState.doorOpen ? "Door or hatch open" : "Doors and hatches closed"; color: T.StyleManager.textSecondary; font.pixelSize: 17 }
                }
            }
        }
    }
}
