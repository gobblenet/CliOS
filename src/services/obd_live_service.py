"""Real-time OBD-II engine data (mode 01) for any compatible vehicle.

Complements the vehicle-specific CAN decoding: standard PIDs are discovered
automatically, then polled in a loop and published to the ``obd`` runtime
domain.
"""

import threading

from src.obd.pids import (
    MONITOR_STATUS_PID, PIDS, SUPPORT_PIDS, decode_monitor_status, decode_pid, decode_supported,
)
from src.obd.transport import CanObdTransport, Elm327Transport
from src.services.base_service import BaseService
from src.services.param_types import ServiceParamType

FAST_TTL_S = 3.0
SLOW_TTL_S = 30.0
NO_ECU_RETRY_S = 5.0
MAX_EMPTY_CYCLES = 5


class NoEcuResponse(Exception):
    pass


class ObdLiveService(BaseService):
    def __init__(self, runtime, storage=None, *, can_transport: CanObdTransport | None = None):
        super().__init__(
            "OBD",
            storage,
            service_id="clios.obd_live",
            description="Standard OBD-II live data (CAN or ELM327)",
        )
        self.runtime = runtime
        self.can_transport = can_transport
        self._thread = None
        self._reconnect = threading.Event()
        self.supported: set[int] = set()

        self.register_param("transport", "Interface", ServiceParamType.LIST, "auto",
                            options=["auto", "can", "elm327"])
        self.register_param("elm_port", "ELM327 port", ServiceParamType.TEXT, "/dev/rfcomm0")
        self.register_param("elm_baud", "ELM327 baud rate", ServiceParamType.LIST, "auto",
                            options=["auto"] + [str(rate) for rate in Elm327Transport.BAUD_CANDIDATES])
        self.register_param("poll_delay_ms", "Pause between cycles (ms)", ServiceParamType.SLIDER, 0.0,
                            min_val=0.0, max_val=1000.0)

    def start(self, stop_event: threading.Event):
        self._thread = threading.Thread(target=self._run, args=(stop_event,), daemon=True, name="ObdLiveWorker")
        self._thread.start()
        super().start(stop_event, implemented=True)

    def on_param_changed(self, key, value):
        if key in ("transport", "elm_port", "elm_baud"):
            self._reconnect.set()

    def _param(self, key):
        return self._params[key]["value"]

    def _should_stop(self, stop_event):
        return stop_event.is_set() or self._reconnect.is_set()

    # ------------------------------------------------------------------ boucle
    def _select_transport(self):
        choice = self._param("transport")
        if choice == "can" or (choice == "auto" and self.can_transport is not None and self.can_transport.connected):
            if self.can_transport is None:
                raise OSError("no CAN bus configured")
            return self.can_transport
        return Elm327Transport(self._param("elm_port"), self._param("elm_baud"))

    def _run(self, stop_event: threading.Event):
        while not stop_event.is_set():
            self._reconnect.clear()
            transport = None
            try:
                transport = self._select_transport()
                transport.open()
                self.poll(transport, stop_event)
            except NoEcuResponse:
                self._publish_status(False, transport)
                self.set_warning("No ECU is responding (ignition off?)")
            except (OSError, ValueError) as exc:
                self._publish_status(False, transport)
                self.set_error(f"OBD unavailable: {exc}")
            finally:
                if transport is not None:
                    transport.close()
            if not self._reconnect.is_set():
                stop_event.wait(NO_ECU_RETRY_S)

    def discover(self, transport) -> set[int]:
        supported: set[int] = set()
        for base in SUPPORT_PIDS:
            if base != 0x00 and base not in supported:
                break
            data = transport.query(base)
            if data is None:
                break
            supported |= decode_supported(base, data)
        if not supported:
            raise NoEcuResponse()
        return supported

    def poll(self, transport, stop_event):
        """Discover PIDs, then poll in a loop until stopped or the ECU is lost."""
        self.supported = self.discover(transport)
        fast = [pid for pid in sorted(self.supported) if pid in PIDS and PIDS[pid].fast]
        slow = [pid for pid in sorted(self.supported) if pid in PIDS and not PIDS[pid].fast]
        if MONITOR_STATUS_PID in self.supported:
            slow.insert(0, MONITOR_STATUS_PID)
        self._publish_status(True, transport)
        self.set_ok(f"{len(fast) + len(slow)} PIDs on {transport.label}")

        cycle = 0
        empty_cycles = 0
        while not self._should_stop(stop_event):
            if self.runtime.snapshot().domain("diagnostics").get("scanning"):
                stop_event.wait(0.2)  # The DTC scan has priority on the bus.
                continue
            # Every fast PID each cycle, plus one slow PID in rotation.
            batch = fast + ([slow[cycle % len(slow)]] if slow else [])
            cycle += 1
            if self.poll_once(transport, batch):
                empty_cycles = 0
            else:
                empty_cycles += 1
                if empty_cycles >= MAX_EMPTY_CYCLES:
                    raise NoEcuResponse()
            delay = self._param("poll_delay_ms") / 1000.0
            if delay > 0:
                stop_event.wait(delay)

    def poll_once(self, transport, pids) -> bool:
        fast_values, slow_values, units = {}, {}, {}
        for pid in pids:
            data = transport.query(pid)
            if data is None:
                continue
            if pid == MONITOR_STATUS_PID:
                slow_values.update(decode_monitor_status(data))
                continue
            value = decode_pid(pid, data)
            if value is None:
                continue
            definition = PIDS[pid]
            (fast_values if definition.fast else slow_values)[definition.key] = value
            if definition.unit:
                units[definition.key] = definition.unit
        if fast_values:
            self.runtime.publish("obd", fast_values, source="obd", ttl_s=FAST_TTL_S, units=units)
        if slow_values:
            self.runtime.publish("obd", slow_values, source="obd", ttl_s=SLOW_TTL_S, units=units)
        return bool(fast_values or slow_values)

    def _publish_status(self, connected, transport):
        self.runtime.publish("obd", {
            "obd_connected": connected,
            "obd_interface": getattr(transport, "label", ""),
            "obd_supported_pids": len(self.supported) if connected else 0,
        }, source="obd", ttl_s=None)
