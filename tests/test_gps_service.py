import threading
import unittest

from src.gps.nmea import NmeaParser, checksum, parse_coordinate, split_sentence
from src.runtime import VehicleRuntime
from src.services.gps_service import GpsService, destination_point


def sentence(body: str) -> str:
    return f"${body}*{checksum(body)}\r\n"


RMC = sentence("GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W")
GGA = sentence("GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,")
RMC_SLOW = sentence("GPRMC,123520,A,4807.038,N,01131.000,E,000.5,270.0,230394,003.1,W")


class MemoryStorage:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class NmeaParserTest(unittest.TestCase):
    def test_checksum_is_required_and_verified(self):
        self.assertIsNotNone(split_sentence(RMC))
        self.assertIsNone(split_sentence(RMC.replace("*", "*0")[:-5] + "*00"))
        self.assertIsNone(split_sentence("$GPRMC,123519,A,4807.038,N"))

    def test_coordinates_convert_to_signed_decimal_degrees(self):
        self.assertAlmostEqual(parse_coordinate("4807.038", "N"), 48.1173, places=4)
        self.assertAlmostEqual(parse_coordinate("01131.000", "W"), -11.516667, places=5)
        self.assertIsNone(parse_coordinate("4875.000", "N"))
        self.assertIsNone(parse_coordinate("", "N"))

    def test_rmc_and_gga_build_a_fix(self):
        parser = NmeaParser()
        self.assertEqual(parser.feed(RMC), "RMC")
        self.assertEqual(parser.feed(GGA), "GGA")
        fix = parser.fix
        self.assertTrue(fix.valid)
        self.assertAlmostEqual(fix.latitude, 48.1173, places=4)
        self.assertAlmostEqual(fix.longitude, 11.516667, places=5)
        self.assertAlmostEqual(fix.speed_kmh, 22.4 * 1.852, places=3)
        self.assertEqual(fix.course_deg, 84.4)
        self.assertEqual(fix.satellites_used, 8)
        self.assertEqual(fix.altitude_m, 545.4)
        self.assertEqual(fix.quality, "GPS")

    def test_void_rmc_keeps_last_position_but_marks_invalid(self):
        parser = NmeaParser()
        parser.feed(RMC)
        parser.feed(sentence("GPRMC,123521,V,,,,,,,230394,,"))
        self.assertFalse(parser.fix.valid)
        self.assertAlmostEqual(parser.fix.latitude, 48.1173, places=4)

    def test_garmin_and_multi_constellation_sentences(self):
        parser = NmeaParser()
        self.assertEqual(parser.feed(sentence("PGRME,15.0,M,45.0,M,25.0,M")), "PGRME")
        self.assertEqual(parser.fix.accuracy_m, 15.0)
        self.assertEqual(parser.feed(sentence("GNGSA,A,3,04,05,,,,,,,,,,,2.5,1.3,2.1")), "GSA")
        self.assertEqual(parser.fix.mode, "3D")
        self.assertEqual(parser.feed(sentence("GPGSV,3,1,11,03,03,111,00,04,15,270,00,06,01,010,00,13,06,292,00")), "GSV")
        self.assertEqual(parser.fix.satellites_in_view, 11)

    def test_garbage_is_counted_not_raised(self):
        parser = NmeaParser()
        self.assertIsNone(parser.feed("\x00\xffnoise"))
        self.assertIsNone(parser.feed(sentence("GPRMC,1")))
        self.assertEqual(parser.fix.rejected, 2)


class GpsServiceTest(unittest.TestCase):
    def setUp(self):
        self.runtime = VehicleRuntime(MemoryStorage())
        self.service = GpsService(self.runtime, MemoryStorage())

    def navigation(self):
        return self.runtime.snapshot().domain("navigation")

    def test_nmea_epoch_publishes_navigation_domain(self):
        self.service.ingest_nmea(RMC)
        self.service.ingest_nmea(GGA)
        nav = self.navigation()
        self.assertTrue(nav["gps_fix"])
        self.assertAlmostEqual(nav["latitude"], 48.1173, places=4)
        self.assertAlmostEqual(nav["gps_speed"], 41.5, places=1)
        self.assertEqual(nav["heading"], 84.4)
        self.assertTrue(nav["heading_valid"])
        self.assertEqual(nav["gps_satellites"], 8)

    def test_heading_is_held_when_stationary(self):
        self.service.ingest_nmea(RMC)
        self.service.ingest_nmea(RMC_SLOW)
        nav = self.navigation()
        self.assertEqual(nav["heading"], 84.4)
        self.assertFalse(nav["heading_valid"])

    def test_gpsd_tpv_and_sky_messages(self):
        self.service.ingest_gpsd({"class": "SKY", "hdop": 1.1, "satellites": [
            {"PRN": 1, "used": True}, {"PRN": 2, "used": True}, {"PRN": 3, "used": False}]})
        self.service.ingest_gpsd({"class": "TPV", "mode": 3, "lat": 45.5, "lon": -73.6,
                                  "altMSL": 30.0, "speed": 10.0, "track": 200.0, "eph": 5.0})
        nav = self.navigation()
        self.assertTrue(nav["gps_fix"])
        self.assertEqual(nav["gps_mode"], "3D")
        self.assertEqual(nav["gps_satellites"], 2)
        self.assertEqual(nav["gps_speed"], 36.0)
        self.assertEqual(nav["heading"], 200.0)
        self.assertEqual(nav["gps_accuracy_m"], 5.0)

    def test_gpsd_without_fix_reports_no_position(self):
        self.service.ingest_gpsd({"class": "TPV", "mode": 1})
        nav = self.navigation()
        self.assertFalse(nav["gps_fix"])
        self.assertNotIn("latitude", nav)

    def test_mock_source_moves_with_runtime_speed(self):
        service = GpsService(self.runtime, MemoryStorage(), mock=True)
        self.runtime.publish("motion", {"speed": 90.0}, source="test")
        stop = threading.Event()
        service.start(stop)
        try:
            for _ in range(50):
                if self.navigation().get("gps_fix"):
                    break
                stop.wait(0.05)
            first = (self.navigation()["latitude"], self.navigation()["longitude"])
            stop.wait(0.6)
            second = (self.navigation()["latitude"], self.navigation()["longitude"])
        finally:
            service.stop()
        self.assertNotEqual(first, second)
        self.assertEqual(self.navigation()["gps_source"], "mock")

    def test_unavailable_serial_port_sets_error_without_crashing(self):
        self.service.update_param("source", "serial")
        self.service.update_param("port", "/dev/does-not-exist-clios")
        stop = threading.Event()
        self.service.start(stop)
        try:
            for _ in range(60):
                if self.service.status.value == "ERROR":
                    break
                stop.wait(0.05)
        finally:
            self.service.stop()
        self.assertEqual(self.service.status.value, "ERROR")
        self.assertFalse(self.navigation()["gps_fix"])

    def test_destination_point_moves_north(self):
        lat, lon = destination_point(48.0, 2.0, 0.0, 1000.0)
        self.assertAlmostEqual(lat, 48.008993, places=5)
        self.assertAlmostEqual(lon, 2.0, places=6)


if __name__ == "__main__":
    unittest.main()
