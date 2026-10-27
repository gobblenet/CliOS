import io
import os
import tempfile
import unittest
from unittest import mock

from src.gps.nmea import checksum
from tools import hardware_check


def sentence(body):
    return f"${body}*{checksum(body)}\r\n".encode("ascii")


class FakeSerial:
    def __init__(self, lines):
        self._stream = io.BytesIO(b"".join(lines))

    def readline(self):
        return self._stream.readline()

    def close(self):
        pass


class HardwareCheckTest(unittest.TestCase):
    def setUp(self):
        handle, self.port = tempfile.mkstemp()
        os.close(handle)
        self.addCleanup(os.remove, self.port)

    def test_gps_passes_with_valid_nmea_and_reports_the_fix(self):
        lines = [sentence("GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W"),
                 sentence("GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,")]
        result = hardware_check.check_gps(self.port, 0.05, open_serial=lambda path, baud: FakeSerial(lines))
        self.assertEqual(result.status, "PASS")
        self.assertIn("4800 baud", result.detail)
        self.assertIn("8 satellites", result.detail)

    def test_gps_tries_every_baud_rate_before_failing(self):
        tried = []

        def open_serial(path, baud):
            tried.append(baud)
            return FakeSerial([b"\x00garbage\r\n"])

        result = hardware_check.check_gps(self.port, 0.01, open_serial=open_serial)
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(tried, list(hardware_check.GPS_BAUDS))

    def test_missing_gps_port_is_skipped(self):
        result = hardware_check.check_gps("/dev/does-not-exist-clios", 0.01, open_serial=None)
        self.assertEqual(result.status, "SKIP")

    def test_permission_error_mentions_dialout(self):
        def open_serial(path, baud):
            raise PermissionError("denied")

        result = hardware_check.check_gps(self.port, 0.01, open_serial=open_serial)
        self.assertEqual(result.status, "FAIL")
        self.assertIn("dialout", result.detail)

    def test_can_states(self):
        with mock.patch.object(hardware_check, "can_interface_state", return_value=None):
            self.assertEqual(hardware_check.check_can("can0").status, "SKIP")
        with mock.patch.object(hardware_check, "can_interface_state", return_value="down"):
            self.assertEqual(hardware_check.check_can("can0").status, "FAIL")
        with mock.patch.object(hardware_check, "can_interface_state", return_value="unknown"):
            self.assertEqual(hardware_check.check_can("can0").status, "PASS")

    def test_pid_discovery_and_sampling(self):
        responses = {0x00: bytes([0x08, 0x18, 0x00, 0x00]), 0x05: bytes([0x7B]), 0x0C: bytes([0x1A, 0xF8]),
                     0x0D: bytes([0x3C])}
        supported = hardware_check.discover_pids(responses.get)
        self.assertTrue({0x05, 0x0C, 0x0D}.issubset(supported))
        readings = hardware_check.sample_readings(responses.get, supported)
        self.assertIn("rpm=1726 rpm", readings)
        self.assertIn("coolant_temp=83 degC", readings)

    def test_obd_over_can_against_a_simulated_ecu(self):
        import threading

        import can

        from src.simulation.models import SimulatedVehicleState, VehicleParameters
        from src.simulation.obd_responder import mode01_responses

        channel = "clios-hardware-check-test"
        state, params = SimulatedVehicleState(), VehicleParameters()
        state.rpm, state.speed_kmh, state.engine_temp_c = 2500.0, 60.0, 90.0
        ecu_bus = can.Bus(interface="virtual", channel=channel)
        stop = threading.Event()

        def ecu():
            while not stop.is_set():
                request = ecu_bus.recv(timeout=0.05)
                if request is not None:
                    for response in mode01_responses(request, state, params):
                        ecu_bus.send(response)

        class VirtualProvider:
            def __init__(self, channel):
                self.channel = channel
                self.bus = None

            def connect(self):
                self.bus = can.Bus(interface="virtual", channel=self.channel)

            def read_frame(self, timeout=0.1):
                return self.bus.recv(timeout)

            def send_frame(self, can_id, data):
                self.bus.send(can.Message(arbitration_id=can_id, data=data, is_extended_id=False))
                return True

            def close(self):
                self.bus.shutdown()

        worker = threading.Thread(target=ecu, daemon=True)
        worker.start()
        try:
            with mock.patch.object(hardware_check, "can_interface_state", return_value="up"), \
                    mock.patch("src.driver.Slcan", VirtualProvider):
                result = hardware_check.check_obd_can(channel)
        finally:
            stop.set()
            worker.join(timeout=1.0)
            ecu_bus.shutdown()
        self.assertEqual(result.status, "PASS", result.detail)
        self.assertIn("rpm=2500 rpm", result.detail)
        self.assertIn("speed=60 km/h", result.detail)

    def test_required_checks_drive_the_exit_code(self):
        skip = hardware_check.Result("GPS", "SKIP", "")
        with mock.patch.object(hardware_check, "check_gps", return_value=skip), \
                mock.patch.object(hardware_check, "default_gps_port", return_value="/dev/null"), \
                mock.patch.object(hardware_check, "check_can", return_value=hardware_check.Result("CAN", "SKIP", "")), \
                mock.patch.object(hardware_check, "check_obd_can",
                                  return_value=hardware_check.Result("OBD (CAN)", "SKIP", "")), \
                mock.patch("builtins.print"):
            self.assertEqual(hardware_check.main([]), 0)
            self.assertEqual(hardware_check.main(["--require-gps"]), 1)
            self.assertEqual(hardware_check.main(["--require-obd"]), 1)


if __name__ == "__main__":
    unittest.main()
