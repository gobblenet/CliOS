import os
import threading
import unittest

from src.obd.pids import PIDS, decode_monitor_status, decode_pid, decode_supported, encode_pid
from src.obd.transport import CanObdTransport, ObdFrameRouter, parse_elm_response
from src.runtime import VehicleRuntime
from src.services.obd_live_service import NoEcuResponse, ObdLiveService
from src.simulation.physique_mock import PhysicsMockProvider


class MemoryStorage:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class PidDecodingTest(unittest.TestCase):
    def test_standard_formulas(self):
        self.assertEqual(decode_pid(0x0C, bytes([0x1A, 0xF8])), 1726.0)
        self.assertEqual(decode_pid(0x05, bytes([0x7B])), 83.0)
        self.assertEqual(decode_pid(0x0D, bytes([0x3C])), 60.0)
        self.assertEqual(decode_pid(0x42, bytes([0x37, 0x6E])), 14.19)
        self.assertAlmostEqual(decode_pid(0x06, bytes([0x80])), 0.0)
        self.assertIsNone(decode_pid(0x0C, bytes([0x1A])))
        self.assertIsNone(decode_pid(0xFE, bytes([0x00])))

    def test_encode_is_inverse_of_decode(self):
        for pid, value in ((0x0C, 3250.0), (0x05, 92.0), (0x2F, 50.0), (0x42, 12.6), (0x10, 21.5)):
            self.assertAlmostEqual(decode_pid(pid, encode_pid(pid, value)), value, delta=0.5)

    def test_supported_bitmask(self):
        supported = decode_supported(0x00, bytes([0xBE, 0x1F, 0xA8, 0x13]))
        self.assertTrue({0x01, 0x03, 0x04, 0x05, 0x0C, 0x0D, 0x20}.issubset(supported))
        self.assertNotIn(0x02, supported)

    def test_monitor_status(self):
        self.assertEqual(decode_monitor_status(bytes([0x83, 0x07])), {"mil_on": True, "dtc_count": 3})

    def test_every_pid_has_unique_key(self):
        keys = [definition.key for definition in PIDS.values()]
        self.assertEqual(len(keys), len(set(keys)))

    def test_every_pid_has_a_ui_label(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "state", "SignalCatalog.js")
        with open(path, encoding="utf-8") as stream:
            catalog = stream.read()
        missing = [d.key for d in PIDS.values() if f'"obd.{d.key}"' not in catalog]
        self.assertEqual(missing, [])

    def test_elm_response_parsing(self):
        self.assertEqual(parse_elm_response("41 0C 1A F8\r\r", 0x0C), bytes([0x1A, 0xF8]))
        self.assertEqual(parse_elm_response("SEARCHING...\r410D3C", 0x0D), bytes([0x3C]))
        self.assertIsNone(parse_elm_response("NO DATA", 0x0C))
        self.assertIsNone(parse_elm_response("41 0D 3C", 0x0C))


class ObdLiveServiceTest(unittest.TestCase):
    def setUp(self):
        self.runtime = VehicleRuntime(MemoryStorage())
        self.provider = PhysicsMockProvider(self.runtime)
        self.transport = CanObdTransport(self.provider, timeout_s=0.05)
        self.provider.register_obd_callback(ObdFrameRouter(self.transport.receive_frame))
        self.provider.is_connected = True  # Bus virtuel sans boucle physique.
        self.service = ObdLiveService(self.runtime, MemoryStorage(), can_transport=self.transport)

    def obd(self):
        return self.runtime.snapshot().domain("obd")

    def test_discovery_and_poll_against_simulated_ecu(self):
        self.provider.engine.state.rpm = 2500.0
        self.provider.engine.state.engine_temp_c = 91.0
        supported = self.service.discover(self.transport)
        self.assertTrue({0x01, 0x05, 0x0C, 0x0D, 0x42}.issubset(supported))
        self.assertTrue(self.service.poll_once(self.transport, [0x0C, 0x05, 0x01]))
        values = self.obd()
        self.assertEqual(values["rpm"], 2500.0)
        self.assertEqual(values["coolant_temp"], 91.0)
        self.assertFalse(values["mil_on"])

    def test_mil_reflects_active_dtcs(self):
        self.provider.engine.state.active_dtcs = ["P0300", "P0171"]
        self.service.poll_once(self.transport, [0x01])
        self.assertTrue(self.obd()["mil_on"])
        self.assertEqual(self.obd()["dtc_count"], 2)

    def test_silent_bus_raises_no_ecu(self):
        self.provider.is_connected = False
        self.transport = CanObdTransport(self.provider, timeout_s=0.01)
        self.provider.send_frame = lambda *_args: True
        with self.assertRaises(NoEcuResponse):
            self.service.discover(self.transport)

    def test_worker_publishes_and_stops(self):
        stop = threading.Event()
        self.service.start(stop)
        try:
            for _ in range(60):
                if "rpm" in self.obd():
                    break
                stop.wait(0.05)
        finally:
            self.service.stop()
        self.assertIn("rpm", self.obd())
        self.assertTrue(self.obd()["obd_connected"])
        self.assertEqual(self.service.status.value, "OK")

    def test_polling_pauses_during_dtc_scan(self):
        self.runtime.publish("diagnostics", {"scanning": True}, source="test")
        stop = threading.Event()
        self.service.start(stop)
        try:
            stop.wait(0.4)
        finally:
            self.service.stop()
        self.assertNotIn("rpm", self.obd())


if __name__ == "__main__":
    unittest.main()
