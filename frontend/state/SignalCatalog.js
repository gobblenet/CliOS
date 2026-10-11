.pragma library

// Libellés lisibles des signaux runtime ("domaine.clé"). Un signal absent
// d'ici reste affichable : son nom est dérivé de la clé.
var labels = {
    "obd.engine_load": "Charge moteur",
    "obd.coolant_temp": "Température liquide",
    "obd.short_fuel_trim_1": "Correction courte B1",
    "obd.long_fuel_trim_1": "Correction longue B1",
    "obd.fuel_pressure": "Pression carburant",
    "obd.intake_pressure": "Pression admission",
    "obd.rpm": "Régime",
    "obd.speed": "Vitesse",
    "obd.timing_advance": "Avance allumage",
    "obd.intake_temp": "Température admission",
    "obd.maf": "Débit d'air",
    "obd.throttle": "Papillon",
    "obd.run_time": "Temps moteur",
    "obd.distance_with_mil": "Distance avec voyant",
    "obd.fuel_rail_pressure": "Pression rampe",
    "obd.egr_commanded": "EGR commandée",
    "obd.fuel_level": "Niveau carburant",
    "obd.distance_since_clear": "Distance depuis effacement",
    "obd.baro_pressure": "Pression atmosphérique",
    "obd.catalyst_temp_b1s1": "Température catalyseur",
    "obd.module_voltage": "Tension batterie",
    "obd.absolute_load": "Charge absolue",
    "obd.commanded_afr": "Lambda commandé",
    "obd.relative_throttle": "Papillon relatif",
    "obd.ambient_temp": "Température extérieure",
    "obd.accel_pedal_d": "Pédale accélérateur",
    "obd.time_with_mil": "Temps avec voyant",
    "obd.ethanol_pct": "Taux d'éthanol",
    "obd.relative_accel_pedal": "Pédale relative",
    "obd.oil_temp": "Température huile",
    "obd.fuel_rate": "Consommation",
    "obd.actual_torque_pct": "Couple réel",
    "obd.mil_on": "Voyant moteur",
    "obd.dtc_count": "Défauts mémorisés",
    "powertrain.rpm": "Régime (CAN)",
    "powertrain.engine_temp": "Température moteur (CAN)",
    "powertrain.fuel_level": "Carburant (CAN)",
    "powertrain.estimated_power_hp": "Puissance estimée",
    "powertrain.estimated_torque_nm": "Couple estimé",
    "motion.speed": "Vitesse (CAN)",
    "motion.odometer": "Kilométrage",
    "environment.outside_temp": "Température extérieure (CAN)",
    "environment.cabin_db_spl": "Bruit habitacle",
    "navigation.gps_speed": "Vitesse GPS",
    "navigation.altitude_m": "Altitude",
    "navigation.heading": "Cap",
    "navigation.gps_satellites": "Satellites GPS"
}

var units = { "degC": "°C", "deg": "°", "rpm": "tr/min" }

// Tableau par défaut : l'essentiel pour surveiller un moteur via OBD-II.
var defaultTiles = [
    { domain: "obd", key: "rpm", low: null, high: null },
    { domain: "obd", key: "speed", low: null, high: null },
    { domain: "obd", key: "coolant_temp", low: null, high: 105 },
    { domain: "obd", key: "module_voltage", low: 12.0, high: 15.0 },
    { domain: "obd", key: "engine_load", low: null, high: null },
    { domain: "obd", key: "intake_temp", low: null, high: 60 },
    { domain: "obd", key: "oil_temp", low: null, high: 125 },
    { domain: "obd", key: "fuel_level", low: 10, high: null },
    { domain: "obd", key: "throttle", low: null, high: null },
    { domain: "obd", key: "maf", low: null, high: null },
    { domain: "obd", key: "fuel_rate", low: null, high: null },
    { domain: "obd", key: "dtc_count", low: null, high: 0 }
]

function label(domain, key) {
    var known = labels[domain + "." + key]
    if (known) return known
    var text = String(key).replace(/_/g, " ")
    return text.charAt(0).toUpperCase() + text.slice(1)
}

function unit(raw) {
    if (!raw) return ""
    return units[raw] !== undefined ? units[raw] : raw
}

function numeric(value) {
    if (value === true) return 1
    if (value === false) return 0
    var parsed = Number(value)
    return isFinite(parsed) ? parsed : NaN
}

// "alarm" si hors bornes, "warning" à moins de 5 % de la plage d'une borne.
function level(tile, value) {
    var number = numeric(value)
    if (isNaN(number)) return "normal"
    var low = tile.low === null || tile.low === undefined ? null : Number(tile.low)
    var high = tile.high === null || tile.high === undefined ? null : Number(tile.high)
    if (high !== null && number > high) return "alarm"
    if (low !== null && number < low) return "alarm"
    var margin = (low !== null && high !== null) ? (high - low) * 0.05 : Math.max(Math.abs(high !== null ? high : low || 0) * 0.05, 0.5)
    if (high !== null && high !== 0 && number > high - margin) return "warning"
    if (low !== null && number < low + margin) return "warning"
    return "normal"
}

function format(value, decimals) {
    if (value === true) return "OUI"
    if (value === false) return "NON"
    var number = Number(value)
    if (value === undefined || value === null || !isFinite(number)) return value === undefined || value === null ? "—" : String(value)
    if (decimals === undefined || decimals < 0) {
        if (Math.round(number) === number) return number.toFixed(0)
        decimals = Math.abs(number) >= 100 ? 0 : (Math.abs(number) >= 10 ? 1 : 2)
    }
    return number.toFixed(decimals)
}
