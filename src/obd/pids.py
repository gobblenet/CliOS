"""Standard OBD-II PID table (SAE J1979, mode 01) and decoding.

Each PID is published to the ``obd`` runtime domain under a stable key.
Fast PIDs (rpm, speed...) are polled every cycle; slow ones (temperatures,
levels, counters) are rotated so one is read per cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PidDefinition:
    pid: int
    key: str
    label: str
    unit: str
    length: int
    decode: Callable[[bytes], float]
    fast: bool = False


def _u16(data: bytes) -> int:
    return data[0] * 256 + data[1]


def _temp(data: bytes) -> float:
    return data[0] - 40.0


def _pct(data: bytes) -> float:
    return data[0] * 100.0 / 255.0


def _trim(data: bytes) -> float:
    return data[0] * 100.0 / 128.0 - 100.0


PIDS: dict[int, PidDefinition] = {
    d.pid: d for d in (
        PidDefinition(0x04, "engine_load", "Engine load", "%", 1, _pct, fast=True),
        PidDefinition(0x05, "coolant_temp", "Coolant temperature", "degC", 1, _temp),
        PidDefinition(0x06, "short_fuel_trim_1", "Short fuel trim B1", "%", 1, _trim),
        PidDefinition(0x07, "long_fuel_trim_1", "Long fuel trim B1", "%", 1, _trim),
        PidDefinition(0x0A, "fuel_pressure", "Fuel pressure", "kPa", 1, lambda d: d[0] * 3.0),
        PidDefinition(0x0B, "intake_pressure", "Intake pressure", "kPa", 1, lambda d: float(d[0]), fast=True),
        PidDefinition(0x0C, "rpm", "Engine speed", "rpm", 2, lambda d: _u16(d) / 4.0, fast=True),
        PidDefinition(0x0D, "speed", "Speed", "km/h", 1, lambda d: float(d[0]), fast=True),
        PidDefinition(0x0E, "timing_advance", "Timing advance", "deg", 1, lambda d: d[0] / 2.0 - 64.0),
        PidDefinition(0x0F, "intake_temp", "Intake air temperature", "degC", 1, _temp),
        PidDefinition(0x10, "maf", "Mass air flow", "g/s", 2, lambda d: _u16(d) / 100.0, fast=True),
        PidDefinition(0x11, "throttle", "Throttle", "%", 1, _pct, fast=True),
        PidDefinition(0x1F, "run_time", "Engine run time", "s", 2, lambda d: float(_u16(d))),
        PidDefinition(0x21, "distance_with_mil", "Distance with MIL on", "km", 2, lambda d: float(_u16(d))),
        PidDefinition(0x23, "fuel_rail_pressure", "Fuel rail pressure", "kPa", 2, lambda d: _u16(d) * 10.0),
        PidDefinition(0x2C, "egr_commanded", "Commanded EGR", "%", 1, _pct),
        PidDefinition(0x2F, "fuel_level", "Fuel level", "%", 1, _pct),
        PidDefinition(0x31, "distance_since_clear", "Distance since codes cleared", "km", 2, lambda d: float(_u16(d))),
        PidDefinition(0x33, "baro_pressure", "Barometric pressure", "kPa", 1, lambda d: float(d[0])),
        PidDefinition(0x3C, "catalyst_temp_b1s1", "Catalyst temperature", "degC", 2, lambda d: _u16(d) / 10.0 - 40.0),
        PidDefinition(0x42, "module_voltage", "Battery voltage", "V", 2, lambda d: _u16(d) / 1000.0),
        PidDefinition(0x43, "absolute_load", "Absolute load", "%", 2, lambda d: _u16(d) * 100.0 / 255.0),
        PidDefinition(0x44, "commanded_afr", "Commanded lambda", "", 2, lambda d: _u16(d) * 2.0 / 65536.0),
        PidDefinition(0x45, "relative_throttle", "Relative throttle", "%", 1, _pct),
        PidDefinition(0x46, "ambient_temp", "Outside temperature", "degC", 1, _temp),
        PidDefinition(0x49, "accel_pedal_d", "Accelerator pedal", "%", 1, _pct, fast=True),
        PidDefinition(0x4D, "time_with_mil", "Time with MIL on", "min", 2, lambda d: float(_u16(d))),
        PidDefinition(0x52, "ethanol_pct", "Ethanol content", "%", 1, _pct),
        PidDefinition(0x5A, "relative_accel_pedal", "Relative pedal", "%", 1, _pct),
        PidDefinition(0x5C, "oil_temp", "Oil temperature", "degC", 1, _temp),
        PidDefinition(0x5E, "fuel_rate", "Fuel rate", "L/h", 2, lambda d: _u16(d) / 20.0, fast=True),
        PidDefinition(0x62, "actual_torque_pct", "Actual torque", "%", 1, lambda d: d[0] - 125.0, fast=True),
    )
}

# Supported-PID bitmasks: 0x00 describes 0x01-0x20, 0x20 describes 0x21-0x40...
SUPPORT_PIDS = (0x00, 0x20, 0x40, 0x60)
MONITOR_STATUS_PID = 0x01
SLOW_EVERY = 10


def decode_supported(base_pid: int, data: bytes) -> set[int]:
    """Decode a 32-bit supported-PID bitmask."""
    if len(data) < 4:
        return set()
    mask = int.from_bytes(data[:4], "big")
    return {base_pid + bit + 1 for bit in range(32) if mask & (1 << (31 - bit))}


def decode_monitor_status(data: bytes) -> dict:
    """PID 01: check-engine light (MIL) and number of stored faults."""
    if not data:
        return {}
    return {"mil_on": bool(data[0] & 0x80), "dtc_count": data[0] & 0x7F}


def decode_pid(pid: int, data: bytes) -> float | None:
    definition = PIDS.get(pid)
    if definition is None or len(data) < definition.length:
        return None
    return round(definition.decode(bytes(data[:definition.length])), 3)


def encode_pid(pid: int, value: float) -> bytes:
    """Inverse of decoding, used by the simulator (--mock) and tests."""
    definition = PIDS[pid]
    best = bytes(definition.length)
    best_error = None
    # The formulas are monotonic, so a binary search is enough.
    low, high = 0, 256 ** definition.length - 1
    while low <= high:
        mid = (low + high) // 2
        raw = mid.to_bytes(definition.length, "big")
        decoded = definition.decode(raw)
        error = abs(decoded - value)
        if best_error is None or error < best_error:
            best, best_error = raw, error
        if decoded < value:
            low = mid + 1
        else:
            high = mid - 1
    return best
