"""Hardware check for a CliOS install: GPS receiver, CAN bus and OBD-II.

Runs on the car computer (typically from the self-hosted runner workflow
`.github/workflows/hardware.yml`) and only needs pyserial and python-can.

Each check reports PASS, FAIL or SKIP. A check given with --require-* makes
the exit code non-zero when it does not pass; other checks are reported
only, so the workflow stays green when the car is simply switched off.
"""

import argparse
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.gps.nmea import NmeaParser  # noqa: E402
from src.obd.pids import PIDS, SUPPORT_PIDS, decode_pid, decode_supported  # noqa: E402

GPS_BAUDS = (4800, 9600, 19200, 38400)


class Result:
    def __init__(self, name, status, detail):
        self.name = name
        self.status = status
        self.detail = detail

    def __str__(self):
        return f"[{self.status:4}] {self.name}: {self.detail}"


def default_gps_port():
    from src.services.gps_service import default_serial_port
    return default_serial_port()


def check_gps(port, seconds, open_serial=None):
    """Probe the serial port at each baud rate and report what the receiver sends."""
    if open_serial is None:
        try:
            import serial
        except ImportError:
            return Result("GPS", "FAIL", "pyserial is not installed")

        def open_serial(path, baud):
            return serial.Serial(path, baud, timeout=1.0)

    if not os.path.exists(port):
        return Result("GPS", "SKIP", f"{port} does not exist (receiver or USB adapter not plugged in)")
    for baud in GPS_BAUDS:
        parser = NmeaParser()
        try:
            link = open_serial(port, baud)
        except OSError as exc:
            return Result("GPS", "FAIL", f"cannot open {port}: {exc} (is the user in the dialout group?)")
        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                parser.feed(link.readline().decode("ascii", errors="replace"))
        finally:
            link.close()
        fix = parser.fix
        if fix.sentences:
            position = (f"fix {fix.mode if fix.mode != 'NO_FIX' else fix.quality}, {fix.satellites_used} satellites, "
                        f"{fix.latitude:.5f}, {fix.longitude:.5f}" if fix.valid and fix.latitude is not None
                        else f"no fix yet, {fix.satellites_in_view} satellites in view")
            return Result("GPS", "PASS", f"{fix.sentences} valid NMEA sentences on {port} at {baud} baud; {position}")
    return Result("GPS", "FAIL", f"no valid NMEA sentence on {port} at {', '.join(map(str, GPS_BAUDS))} baud "
                                 "(check the RS-232 wiring and receiver power)")


def can_interface_state(interface):
    path = f"/sys/class/net/{interface}/operstate"
    if not os.path.exists(f"/sys/class/net/{interface}"):
        return None
    try:
        with open(path, encoding="ascii") as stream:
            return stream.read().strip()
    except OSError:
        return "unknown"


def check_can(interface):
    state = can_interface_state(interface)
    if state is None:
        return Result("CAN", "SKIP", f"{interface} does not exist (adapter not set up)")
    # SocketCAN interfaces often report "unknown" while working; only "down" is a failure.
    if state == "down":
        return Result("CAN", "FAIL", f"{interface} is down (run: sudo ip link set {interface} up type can bitrate 500000)")
    return Result("CAN", "PASS", f"{interface} is {state}")


def discover_pids(query):
    supported = set()
    for base in SUPPORT_PIDS:
        if base != 0x00 and base not in supported:
            break
        data = query(base)
        if data is None:
            break
        supported |= decode_supported(base, data)
    return supported


def sample_readings(query, supported):
    readings = []
    for pid in (0x0C, 0x0D, 0x05, 0x42):
        if pid in supported:
            value = decode_pid(pid, query(pid) or b"")
            if value is not None:
                definition = PIDS[pid]
                readings.append(f"{definition.key}={value:g}{definition.unit and ' ' + definition.unit}")
    return readings


def check_obd_can(interface):
    if can_interface_state(interface) in (None, "down"):
        return Result("OBD (CAN)", "SKIP", f"{interface} is not available")
    from src.driver import Slcan
    from src.obd.transport import OBD_RESPONSE_IDS, CanObdTransport

    provider = Slcan(channel=interface)
    try:
        provider.connect()
    except RuntimeError as exc:
        return Result("OBD (CAN)", "FAIL", str(exc))
    transport = CanObdTransport(provider, timeout_s=0.3)
    stop = threading.Event()

    def pump():
        while not stop.is_set():
            try:
                frame = provider.read_frame(timeout=0.05)
            except RuntimeError:
                return
            if frame is not None and frame.arbitration_id in OBD_RESPONSE_IDS:
                transport.receive_frame(frame)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    try:
        supported = discover_pids(transport.query)
        if not supported:
            return Result("OBD (CAN)", "SKIP", "no ECU answered (ignition off, or the bus is not the OBD port)")
        readings = sample_readings(transport.query, supported)
        return Result("OBD (CAN)", "PASS", f"{len(supported)} supported PIDs; " + (", ".join(readings) or "no sample"))
    finally:
        stop.set()
        reader.join(timeout=1.0)
        provider.close()


def check_obd_elm(port):
    if not os.path.exists(port):
        return Result("OBD (ELM327)", "SKIP", f"{port} does not exist")
    from src.obd.transport import Elm327Transport

    transport = Elm327Transport(port)
    try:
        transport.open()
    except OSError as exc:
        return Result("OBD (ELM327)", "FAIL", str(exc))
    try:
        supported = discover_pids(transport.query)
        if not supported:
            return Result("OBD (ELM327)", "SKIP", "adapter answered but no ECU did (ignition off?)")
        readings = sample_readings(transport.query, supported)
        return Result("OBD (ELM327)", "PASS",
                      f"{transport.label}: {len(supported)} supported PIDs; " + (", ".join(readings) or "no sample"))
    finally:
        transport.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check the GPS receiver, CAN bus and OBD-II connection")
    parser.add_argument("--gps-port", default="", help="GPS serial device (default: first USB serial adapter)")
    parser.add_argument("--gps-seconds", type=float, default=3.0, help="seconds to listen per baud rate")
    parser.add_argument("--can", default="can0", help="SocketCAN interface")
    parser.add_argument("--elm-port", default="", help="ELM327 serial device (checked only when given)")
    parser.add_argument("--require-gps", action="store_true", help="fail unless the GPS check passes")
    parser.add_argument("--require-can", action="store_true", help="fail unless the CAN check passes")
    parser.add_argument("--require-obd", action="store_true", help="fail unless an OBD check passes")
    args = parser.parse_args(argv)

    results = [
        check_gps(args.gps_port or default_gps_port(), args.gps_seconds),
        check_can(args.can),
        check_obd_can(args.can),
    ]
    if args.elm_port:
        results.append(check_obd_elm(args.elm_port))
    for result in results:
        print(result)

    by_name = {result.name: result.status for result in results}
    failures = []
    if args.require_gps and by_name["GPS"] != "PASS":
        failures.append("GPS")
    if args.require_can and by_name["CAN"] != "PASS":
        failures.append("CAN")
    if args.require_obd and "PASS" not in (by_name.get("OBD (CAN)"), by_name.get("OBD (ELM327)")):
        failures.append("OBD")
    if failures:
        print(f"Required checks failed: {', '.join(failures)}")
        return 1
    print("Hardware check finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
