"""Strict ISO-TP receive-side reassembly for classic 8-byte CAN frames."""

from __future__ import annotations

from dataclasses import dataclass


class IsoTpError(ValueError):
    pass


@dataclass
class IsoTpFlow:
    expected_length: int
    payload: bytearray
    next_sequence: int
    deadline: float


@dataclass(frozen=True)
class IsoTpResult:
    response_id: int
    payload: bytes | None = None
    flow_control_id: int | None = None


class IsoTpReassembler:
    """Maintains an independent ISO-TP stream for each physical ECU."""

    def __init__(self, flow_timeout_s: float = 0.75):
        self.flow_timeout_s = flow_timeout_s
        self.flows: dict[int, IsoTpFlow] = {}

    def feed(self, response_id: int, data, now: float) -> IsoTpResult:
        if not 0x7E8 <= response_id <= 0x7EF:
            raise IsoTpError(f"source ECU out of range: 0x{response_id:X}")
        raw = bytes(data)
        if not raw or len(raw) > 8:
            raise IsoTpError(f"0x{response_id:03X}: invalid frame size ({len(raw)})")

        frame_type = raw[0] >> 4
        if frame_type == 0:
            length = raw[0] & 0x0F
            if length == 0 or length > 7 or length > len(raw) - 1:
                raise IsoTpError(f"0x{response_id:03X}: invalid Single Frame length ({length})")
            self.flows.pop(response_id, None)
            return IsoTpResult(response_id=response_id, payload=raw[1:1 + length])

        if frame_type == 1:
            if len(raw) != 8:
                raise IsoTpError(f"0x{response_id:03X}: incomplete classic First Frame")
            length = ((raw[0] & 0x0F) << 8) | raw[1]
            if length <= 7 or length > 4095:
                raise IsoTpError(f"0x{response_id:03X}: invalid First Frame length ({length})")
            initial = bytearray(raw[2:])
            if len(initial) >= length:
                raise IsoTpError(f"0x{response_id:03X}: inconsistent First Frame ({length})")
            self.flows[response_id] = IsoTpFlow(
                expected_length=length,
                payload=initial,
                next_sequence=1,
                deadline=now + self.flow_timeout_s,
            )
            return IsoTpResult(response_id=response_id, flow_control_id=response_id - 8)

        if frame_type == 2:
            flow = self.flows.get(response_id)
            if flow is None:
                raise IsoTpError(f"0x{response_id:03X}: Consecutive Frame without a flow")
            if now > flow.deadline:
                self.flows.pop(response_id, None)
                raise IsoTpError(f"0x{response_id:03X}: flow timed out")
            sequence = raw[0] & 0x0F
            if sequence != flow.next_sequence:
                self.flows.pop(response_id, None)
                raise IsoTpError(
                    f"0x{response_id:03X}: sequence {sequence:X}, expected {flow.next_sequence:X}"
                )
            if len(raw) < 2:
                self.flows.pop(response_id, None)
                raise IsoTpError(f"0x{response_id:03X}: empty Consecutive Frame")
            remaining = flow.expected_length - len(flow.payload)
            flow.payload.extend(raw[1:1 + min(7, remaining)])
            flow.next_sequence = (flow.next_sequence + 1) & 0x0F
            flow.deadline = now + self.flow_timeout_s
            if len(flow.payload) >= flow.expected_length:
                payload = bytes(flow.payload[:flow.expected_length])
                self.flows.pop(response_id, None)
                return IsoTpResult(response_id=response_id, payload=payload)
            return IsoTpResult(response_id=response_id)

        raise IsoTpError(f"0x{response_id:03X}: unsupported PCI type ({frame_type})")

    def expire(self, now: float) -> list[int]:
        expired = [response_id for response_id, flow in self.flows.items() if now > flow.deadline]
        for response_id in expired:
            self.flows.pop(response_id, None)
        return expired
