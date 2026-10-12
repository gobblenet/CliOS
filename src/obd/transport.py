"""OBD-II mode 01 transports: direct CAN bus (ISO 15765-4) or ELM327 adapter."""

from __future__ import annotations

import collections
import threading
import time

OBD_BROADCAST_ID = 0x7DF
OBD_RESPONSE_IDS = range(0x7E8, 0x7F0)


class ObdFrameRouter:
    """Fan ECU responses 0x7E8-0x7EF out to several consumers.

    CanService only knows a single OBD callback; diagnostics (mode 03) and
    live data (mode 01) both listen to these frames.
    """

    def __init__(self, *listeners):
        self._listeners = list(listeners)

    def add(self, listener):
        self._listeners.append(listener)

    def __call__(self, frame):
        for listener in self._listeners:
            listener(frame)


class CanObdTransport:
    """Single-frame mode 01 requests on the CAN bus shared with CanService."""

    def __init__(self, provider, timeout_s: float = 0.15):
        self.provider = provider
        self.timeout_s = timeout_s
        self._frames = collections.deque(maxlen=64)
        self._event = threading.Event()
        self.label = f"can:{getattr(provider, 'channel', '?')}"

    @property
    def connected(self) -> bool:
        return bool(getattr(self.provider, "is_connected", False))

    def open(self):
        if not self.connected:
            raise OSError("CAN bus not connected")

    def close(self):
        pass

    def receive_frame(self, frame):
        data = bytes(frame.data)
        # Only single-frame mode 01 responses (0x41) matter here.
        if len(data) >= 3 and data[0] >> 4 == 0 and data[1] == 0x41:
            self._frames.append(data)
            self._event.set()

    def query(self, pid: int) -> bytes | None:
        self._frames.clear()
        self._event.clear()
        if not self.provider.send_frame(OBD_BROADCAST_ID, [0x02, 0x01, pid, 0x55, 0x55, 0x55, 0x55, 0x55]):
            raise OSError("CAN write failed")
        deadline = time.monotonic() + self.timeout_s
        while True:
            while self._frames:
                data = self._frames.popleft()
                length = data[0] & 0x0F
                if data[2] == pid and length >= 2:
                    return data[3:1 + length]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self._event.wait(remaining)
            self._event.clear()


class Elm327Transport:
    """Serial ELM327 adapter (USB, Bluetooth rfcomm or PiCCANTE in ELM mode)."""

    BAUD_CANDIDATES = (38400, 115200, 9600, 500000)

    def __init__(self, port: str, baud: str = "auto", timeout_s: float = 1.0):
        self.port = port
        self.baud = baud
        self.timeout_s = timeout_s
        self._link = None
        self.label = f"elm327:{port}"

    @property
    def connected(self) -> bool:
        return self._link is not None

    def open(self):
        try:
            import serial
        except ImportError as exc:
            raise OSError("pyserial absent") from exc
        rates = self.BAUD_CANDIDATES if self.baud == "auto" else (int(self.baud),)
        last_error = "no ELM327 response"
        for rate in rates:
            try:
                link = serial.Serial(self.port, rate, timeout=self.timeout_s)
            except serial.SerialException as exc:
                raise OSError(str(exc)) from exc
            self._link = link
            try:
                if "ELM" in self.command("ATZ", wait_s=1.5).upper():
                    for setup in ("ATE0", "ATL0", "ATS0", "ATH0", "ATSP0"):
                        self.command(setup)
                    self.label = f"elm327:{self.port}@{rate}"
                    return
            except OSError as exc:
                last_error = str(exc)
            link.close()
            self._link = None
        raise OSError(f"{self.port} : {last_error}")

    def close(self):
        if self._link is not None:
            try:
                self._link.close()
            finally:
                self._link = None

    def command(self, text: str, wait_s: float | None = None) -> str:
        if self._link is None:
            raise OSError("ELM327 not connected")
        try:
            self._link.reset_input_buffer()
            self._link.write((text + "\r").encode("ascii"))
            deadline = time.monotonic() + (wait_s or self.timeout_s * 3)
            buffer = b""
            while time.monotonic() < deadline:
                chunk = self._link.read(self._link.in_waiting or 1)
                buffer += chunk
                if b">" in buffer:
                    break
        except Exception as exc:  # SerialException on USB/BT disconnect
            self.close()
            raise OSError(f"ELM327 link lost: {exc}") from exc
        return buffer.decode("ascii", errors="replace").replace(">", "").strip()

    def query(self, pid: int) -> bytes | None:
        return parse_elm_response(self.command(f"01{pid:02X}"), pid)


def parse_elm_response(response: str, pid: int) -> bytes | None:
    """Extract the data bytes from an ELM327 response like "41 0C 1A F8"."""
    marker = f"41{pid:02X}"
    for line in response.replace(" ", "").upper().splitlines():
        line = line.strip()
        index = line.find(marker)
        if index < 0:
            continue
        payload = line[index + len(marker):]
        try:
            return bytes.fromhex(payload[: len(payload) // 2 * 2])
        except ValueError:
            continue
    return None
