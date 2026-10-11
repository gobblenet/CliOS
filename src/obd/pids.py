"""Table des PID OBD-II standard (SAE J1979, mode 01) et décodage.

Chaque PID est publié dans le domaine runtime ``obd`` sous une clé stable.
Les PID rapides (régime, vitesse...) sont interrogés à chaque cycle, les
lents (températures, niveaux, compteurs) une fois tous les ``SLOW_EVERY``.
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
        PidDefinition(0x04, "engine_load", "Charge moteur", "%", 1, _pct, fast=True),
        PidDefinition(0x05, "coolant_temp", "Température liquide", "degC", 1, _temp),
        PidDefinition(0x06, "short_fuel_trim_1", "Correction courte B1", "%", 1, _trim),
        PidDefinition(0x07, "long_fuel_trim_1", "Correction longue B1", "%", 1, _trim),
        PidDefinition(0x0A, "fuel_pressure", "Pression carburant", "kPa", 1, lambda d: d[0] * 3.0),
        PidDefinition(0x0B, "intake_pressure", "Pression admission", "kPa", 1, lambda d: float(d[0]), fast=True),
        PidDefinition(0x0C, "rpm", "Régime", "rpm", 2, lambda d: _u16(d) / 4.0, fast=True),
        PidDefinition(0x0D, "speed", "Vitesse", "km/h", 1, lambda d: float(d[0]), fast=True),
        PidDefinition(0x0E, "timing_advance", "Avance allumage", "deg", 1, lambda d: d[0] / 2.0 - 64.0),
        PidDefinition(0x0F, "intake_temp", "Température admission", "degC", 1, _temp),
        PidDefinition(0x10, "maf", "Débit d'air", "g/s", 2, lambda d: _u16(d) / 100.0, fast=True),
        PidDefinition(0x11, "throttle", "Papillon", "%", 1, _pct, fast=True),
        PidDefinition(0x1F, "run_time", "Temps moteur", "s", 2, lambda d: float(_u16(d))),
        PidDefinition(0x21, "distance_with_mil", "Distance avec voyant", "km", 2, lambda d: float(_u16(d))),
        PidDefinition(0x23, "fuel_rail_pressure", "Pression rampe", "kPa", 2, lambda d: _u16(d) * 10.0),
        PidDefinition(0x2C, "egr_commanded", "EGR commandée", "%", 1, _pct),
        PidDefinition(0x2F, "fuel_level", "Niveau carburant", "%", 1, _pct),
        PidDefinition(0x31, "distance_since_clear", "Distance depuis effacement", "km", 2, lambda d: float(_u16(d))),
        PidDefinition(0x33, "baro_pressure", "Pression atmosphérique", "kPa", 1, lambda d: float(d[0])),
        PidDefinition(0x3C, "catalyst_temp_b1s1", "Température catalyseur", "degC", 2, lambda d: _u16(d) / 10.0 - 40.0),
        PidDefinition(0x42, "module_voltage", "Tension batterie", "V", 2, lambda d: _u16(d) / 1000.0),
        PidDefinition(0x43, "absolute_load", "Charge absolue", "%", 2, lambda d: _u16(d) * 100.0 / 255.0),
        PidDefinition(0x44, "commanded_afr", "Lambda commandé", "", 2, lambda d: _u16(d) * 2.0 / 65536.0),
        PidDefinition(0x45, "relative_throttle", "Papillon relatif", "%", 1, _pct),
        PidDefinition(0x46, "ambient_temp", "Température extérieure", "degC", 1, _temp),
        PidDefinition(0x49, "accel_pedal_d", "Pédale accélérateur", "%", 1, _pct, fast=True),
        PidDefinition(0x4D, "time_with_mil", "Temps avec voyant", "min", 2, lambda d: float(_u16(d))),
        PidDefinition(0x52, "ethanol_pct", "Taux d'éthanol", "%", 1, _pct),
        PidDefinition(0x5A, "relative_accel_pedal", "Pédale relative", "%", 1, _pct),
        PidDefinition(0x5C, "oil_temp", "Température huile", "degC", 1, _temp),
        PidDefinition(0x5E, "fuel_rate", "Consommation", "L/h", 2, lambda d: _u16(d) / 20.0, fast=True),
        PidDefinition(0x62, "actual_torque_pct", "Couple réel", "%", 1, lambda d: d[0] - 125.0, fast=True),
    )
}

# Bitmasks des PID supportés : 0x00 décrit 0x01-0x20, 0x20 décrit 0x21-0x40...
SUPPORT_PIDS = (0x00, 0x20, 0x40, 0x60)
MONITOR_STATUS_PID = 0x01
SLOW_EVERY = 10


def decode_supported(base_pid: int, data: bytes) -> set[int]:
    """Décode un bitmask 32 bits des PID supportés."""
    if len(data) < 4:
        return set()
    mask = int.from_bytes(data[:4], "big")
    return {base_pid + bit + 1 for bit in range(32) if mask & (1 << (31 - bit))}


def decode_monitor_status(data: bytes) -> dict:
    """PID 01 : voyant moteur (MIL) et nombre de défauts mémorisés."""
    if not data:
        return {}
    return {"mil_on": bool(data[0] & 0x80), "dtc_count": data[0] & 0x7F}


def decode_pid(pid: int, data: bytes) -> float | None:
    definition = PIDS.get(pid)
    if definition is None or len(data) < definition.length:
        return None
    return round(definition.decode(bytes(data[:definition.length])), 3)


def encode_pid(pid: int, value: float) -> bytes:
    """Inverse du décodage, utilisé par le simulateur (--mock) et les tests."""
    definition = PIDS[pid]
    best = bytes(definition.length)
    best_error = None
    # Les formules sont monotones : une recherche dichotomique suffit.
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
