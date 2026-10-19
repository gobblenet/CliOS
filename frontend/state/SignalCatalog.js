.pragma library

// Readable labels for runtime signals ("domain.key"). A signal missing
// from this list can still be shown: its name is derived from the key.
var labels = {
    "obd.engine_load": "Engine load",
    "obd.coolant_temp": "Coolant temperature",
    "obd.short_fuel_trim_1": "Short fuel trim B1",
    "obd.long_fuel_trim_1": "Long fuel trim B1",
    "obd.fuel_pressure": "Fuel pressure",
    "obd.intake_pressure": "Intake pressure",
    "obd.rpm": "Engine speed",
    "obd.speed": "Speed",
    "obd.timing_advance": "Timing advance",
    "obd.intake_temp": "Intake air temperature",
    "obd.maf": "Mass air flow",
    "obd.throttle": "Throttle",
    "obd.run_time": "Engine run time",
    "obd.distance_with_mil": "Distance with MIL on",
    "obd.fuel_rail_pressure": "Fuel rail pressure",
    "obd.egr_commanded": "Commanded EGR",
    "obd.fuel_level": "Fuel level",
    "obd.distance_since_clear": "Distance since codes cleared",
    "obd.baro_pressure": "Barometric pressure",
    "obd.catalyst_temp_b1s1": "Catalyst temperature",
    "obd.module_voltage": "Battery voltage",
    "obd.absolute_load": "Absolute load",
    "obd.commanded_afr": "Commanded lambda",
    "obd.relative_throttle": "Relative throttle",
    "obd.ambient_temp": "Outside temperature",
    "obd.accel_pedal_d": "Accelerator pedal",
    "obd.time_with_mil": "Time with MIL on",
    "obd.ethanol_pct": "Ethanol content",
    "obd.relative_accel_pedal": "Relative pedal",
    "obd.oil_temp": "Oil temperature",
    "obd.fuel_rate": "Fuel rate",
    "obd.actual_torque_pct": "Actual torque",
    "obd.mil_on": "Check-engine light",
    "obd.dtc_count": "Stored fault codes",
    "powertrain.rpm": "Engine speed (CAN)",
    "powertrain.engine_temp": "Engine temperature (CAN)",
    "powertrain.fuel_level": "Fuel (CAN)",
    "powertrain.estimated_power_hp": "Estimated power",
    "powertrain.estimated_torque_nm": "Estimated torque",
    "motion.speed": "Speed (CAN)",
    "motion.odometer": "Odometer",
    "environment.outside_temp": "Outside temperature (CAN)",
    "environment.cabin_db_spl": "Cabin noise",
    "navigation.gps_speed": "GPS speed",
    "navigation.altitude_m": "Altitude",
    "navigation.heading": "Heading",
    "navigation.gps_satellites": "GPS satellites"
}

var units = { "degC": "°C", "degF": "°F", "deg": "°", "rpm": "rpm" }

// Default layout: the essentials for watching an engine over OBD-II.
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

// "alarm" when out of range, "warning" within 5 % of a limit.
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
    if (value === true) return "YES"
    if (value === false) return "NO"
    var number = Number(value)
    if (value === undefined || value === null || !isFinite(number)) return value === undefined || value === null ? "—" : String(value)
    if (decimals === undefined || decimals < 0) {
        if (Math.round(number) === number) return number.toFixed(0)
        decimals = Math.abs(number) >= 100 ? 0 : (Math.abs(number) >= 10 ? 1 : 2)
    }
    return number.toFixed(decimals)
}
