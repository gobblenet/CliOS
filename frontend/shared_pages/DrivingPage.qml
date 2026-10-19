import QtQuick
import QtQuick.Layouts
import "components"
import "../style" as T
import "../state" as S

Item {
    id: root
    signal actionRequested(string action)
    function adjustFuelPrice(delta) {
        // The price is shown and adjusted per display volume unit, stored per liter.
        const shown = S.UiState.toPrice(S.UiState.number(S.UiState.fuelPrice, 1.70))
        const perLiter = S.UiState.fromPrice(Math.round((shown + delta) * 100) / 100)
        const next = Math.max(0.50, Math.min(3.50, perLiter))
        root.actionRequested("set_fuel_price:" + next.toFixed(4))
    }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 20; spacing: 14
        PageHeader { Layout.fillWidth: true; title: "Driving"; subtitle: "Current trip and essential vehicle status"; showBack: false }
        RowLayout {
            Layout.fillWidth: true; Layout.minimumHeight: 210; Layout.preferredHeight: 210; Layout.maximumHeight: 210; spacing: 14
            Card { Layout.fillWidth: true; Layout.fillHeight: true; title: "Trip A"
                Metric { anchors.centerIn: parent; width: parent.width; label: "Distance"; value: S.UiState.fixed(S.UiState.toDistance(S.UiState.tripA), 1, "0.0"); unit: S.UiState.distanceUnit; alignment: Text.AlignHCenter; valueSize: 40 }
            }
            Card { Layout.fillWidth: true; Layout.fillHeight: true; title: "Trip B"
                Metric { anchors.centerIn: parent; width: parent.width; label: "Average " + S.UiState.fixed(S.UiState.toConsumption(S.UiState.avgConsB), 1, "—") + " " + S.UiState.consumptionUnit; value: S.UiState.fixed(S.UiState.toDistance(S.UiState.tripB), 1, "0.0"); unit: S.UiState.distanceUnit; alignment: Text.AlignHCenter; valueSize: 40 }
            }
            Card { Layout.fillWidth: true; Layout.fillHeight: true; title: "Session"; highlighted: S.UiState.tripActive
                Column { anchors.centerIn: parent; spacing: 8
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: S.UiState.sessionState; color: S.UiState.tripActive ? T.StyleManager.success : T.StyleManager.textSecondary; font.pixelSize: 30; font.bold: true }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: S.UiState.fixed(S.UiState.toDistance(S.UiState.tripDistance), 1, "0.0") + " " + S.UiState.distanceUnit + " · " + S.UiState.fixed(S.UiState.toConsumption(S.UiState.avgConsSession), 1, "—") + " " + S.UiState.consumptionUnit; color: T.StyleManager.textSecondary; font.pixelSize: 16 }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Estimated cost  " + S.UiState.money(S.UiState.tripCost); color: T.StyleManager.textSecondary; font.pixelSize: 15 }
                }
            }
        }
        Card {
            Layout.fillWidth: true; Layout.minimumHeight: 132; Layout.preferredHeight: 132; Layout.maximumHeight: 132; title: "Trip controls"
            RowLayout { anchors.fill: parent; spacing: 12
                Button { Layout.fillWidth: true; Layout.fillHeight: true; text: "RESET A"; onClicked: root.actionRequested("reset_a") }
                Button { Layout.fillWidth: true; Layout.fillHeight: true; text: "RESET B"; onClicked: root.actionRequested("reset_b") }
                Button { Layout.fillWidth: true; Layout.fillHeight: true; primary: true; text: S.UiState.sessionState === "PAUSED" ? "RESUME" : "PAUSE"; enabled: S.UiState.tripActive || S.UiState.sessionState === "PAUSED"; onClicked: root.actionRequested(S.UiState.sessionState === "PAUSED" ? "resume_trip" : "pause_trip") }
                Button { Layout.fillWidth: true; Layout.fillHeight: true; destructive: true; text: "END TRIP"; enabled: S.UiState.tripActive || S.UiState.sessionState === "PAUSED"; onClicked: root.actionRequested("end_trip") }
            }
        }
        Card {
            Layout.fillWidth: true; Layout.fillHeight: true; title: "Vehicle status summary"
            RowLayout { anchors.fill: parent; spacing: 12
                Metric { Layout.fillWidth: true; Layout.preferredWidth: 180; Layout.minimumWidth: 150; label: "Fuel"; value: S.UiState.fixed(S.UiState.fuelLevel, 0, "—"); unit: "%"; alignment: Text.AlignHCenter }
                Metric { Layout.fillWidth: true; Layout.preferredWidth: 180; Layout.minimumWidth: 150; label: "Range"; value: S.UiState.fixed(S.UiState.toDistance(S.UiState.autonomy), 0, "—"); unit: S.UiState.distanceUnit; alignment: Text.AlignHCenter }
                Metric { Layout.fillWidth: true; Layout.preferredWidth: 180; Layout.minimumWidth: 150; label: "Engine"; value: S.UiState.fixed(S.UiState.toTemperature(S.UiState.engineTemp), 0, "—"); unit: S.UiState.temperatureUnit; alignment: Text.AlignHCenter }
                Metric { Layout.fillWidth: true; Layout.preferredWidth: 180; Layout.minimumWidth: 150; label: "Service in"; value: S.UiState.fixed(S.UiState.toDistance(S.UiState.kmBeforeService), 0, "—"); unit: S.UiState.distanceUnit; alignment: Text.AlignHCenter }
                ColumnLayout { Layout.fillWidth: true; Layout.preferredWidth: 180; Layout.minimumWidth: 150; spacing: 8
                    Text { Layout.alignment: Qt.AlignHCenter; text: S.UiState.attentionVehicle || S.UiState.engineWarning ? "WARNING" : "VEHICLE OK"; color: S.UiState.attentionVehicle || S.UiState.engineWarning ? T.StyleManager.warning : T.StyleManager.success; font.pixelSize: 23; font.bold: true }
                    Text { Layout.fillWidth: true; text: S.UiState.doorOpen ? "Door or hatch open" : (S.UiState.driverUnbelted ? "Driver seatbelt" : "No priority alerts"); color: T.StyleManager.textSecondary; font.pixelSize: 14; horizontalAlignment: Text.AlignHCenter }
                }
                ColumnLayout { Layout.fillWidth: true; Layout.preferredWidth: 180; Layout.minimumWidth: 150; spacing: 8
                    Text { Layout.fillWidth: true; text: "FUEL PRICE"; color: T.StyleManager.textSecondary; font.pixelSize: 14; font.bold: true; horizontalAlignment: Text.AlignHCenter }
                    Text { Layout.fillWidth: true; text: S.UiState.currency + S.UiState.fixed(S.UiState.toPrice(S.UiState.fuelPrice), 2, "—") + "/" + S.UiState.volumeUnit; color: T.StyleManager.text; font.pixelSize: 24; font.bold: true; horizontalAlignment: Text.AlignHCenter }
                    RowLayout { Layout.alignment: Qt.AlignHCenter; spacing: 8
                        Button { Layout.preferredWidth: 64; Layout.minimumHeight: 56; Layout.maximumHeight: 56; text: "−"; onClicked: root.adjustFuelPrice(-0.01) }
                        Button { Layout.preferredWidth: 64; Layout.minimumHeight: 56; Layout.maximumHeight: 56; text: "+"; onClicked: root.adjustFuelPrice(0.01) }
                    }
                }
                ColumnLayout { Layout.fillWidth: true; Layout.preferredWidth: 180; Layout.minimumWidth: 150; spacing: 8
                    Text { Layout.fillWidth: true; text: "UNITS"; color: T.StyleManager.textSecondary; font.pixelSize: 14; font.bold: true; horizontalAlignment: Text.AlignHCenter }
                    Button {
                        objectName: "unitsToggle"
                        Layout.fillWidth: true; Layout.minimumHeight: 72; Layout.maximumHeight: 72
                        text: S.UiState.imperial ? "US" : "METRIC"
                        subtext: S.UiState.imperial ? "mph · MPG · °F · $" : "km/h · L/100 · °C · €"
                        onClicked: bridge.save_setting("ui.units", S.UiState.imperial ? "metric" : "imperial")
                    }
                }
            }
        }
    }
}
