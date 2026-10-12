"""Simulator OBD-II mode 01 responder: standard PIDs computed from the physics."""

from __future__ import annotations

import time

import can

from src.obd.pids import SUPPORT_PIDS, encode_pid


def _values(state, params) -> dict[int, float]:
    max_torque = max(1.0, params.torque_at_rpm(state.rpm))
    load = max(0.0, min(100.0, state.engine_torque_nm / max_torque * 100.0))
    return {
        0x04: load,
        0x05: state.engine_temp_c,
        0x0B: 30.0 + 0.7 * state.throttle_pedal,
        0x0C: state.rpm,
        0x0D: max(0.0, state.speed_kmh),
        0x0F: state.outside_temp_c + 8.0,
        0x10: state.rpm * (0.15 + state.throttle_pedal / 100.0) * 0.012,
        0x11: state.throttle_pedal,
        0x2F: state.fuel_level_l / max(1.0, params.fuel_capacity_l) * 100.0,
        0x42: state.battery_voltage,
        0x46: state.outside_temp_c,
        0x5C: state.engine_temp_c + 6.0,
        0x5E: state.fuel_flow_lph,
    }


def _supported_mask(base: int, available: set[int]) -> bytes:
    mask = 0
    for bit in range(32):
        pid = base + bit + 1
        if pid in available:
            mask |= 1 << (31 - bit)
    return mask.to_bytes(4, "big")


def _frame(payload: bytes) -> can.Message:
    data = bytearray([len(payload)]) + bytearray(payload)
    data += bytearray([0xAA] * (8 - len(data)))
    return can.Message(arbitration_id=0x7E8, data=data, is_extended_id=False, timestamp=time.time())


def mode01_responses(request: can.Message, state, params) -> list[can.Message]:
    """Single-frame response to a mode 01 request, or [] if not applicable."""
    data = bytes(request.data)
    if request.arbitration_id not in (0x7DF, 0x7E0) or len(data) < 3:
        return []
    if not 2 <= data[0] <= 7 or data[1] != 0x01:
        return []
    pid = data[2]
    values = _values(state, params)
    available = set(values) | {0x01}
    available |= {base for base in SUPPORT_PIDS[1:] if any(p > base for p in available)}
    if pid in SUPPORT_PIDS:
        if pid != 0x00 and pid not in available:
            return []
        return [_frame(bytes([0x41, pid]) + _supported_mask(pid, available))]
    if pid == 0x01:
        dtcs = len(getattr(state, "active_dtcs", []) or [])
        return [_frame(bytes([0x41, 0x01, (0x80 if dtcs else 0) | min(dtcs, 0x7F), 0x07, 0xE5, 0x00]))]
    if pid not in values:
        return []
    return [_frame(bytes([0x41, pid]) + encode_pid(pid, values[pid]))]
