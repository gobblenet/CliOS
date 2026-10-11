"""Service GPS : position, cap et qualité de fix publiés dans le domaine navigation.

Sources prises en charge :
- serial : récepteur NMEA 0183 direct (Garmin GPS 17x HVS via adaptateur USB-RS232) ;
- gpsd   : démon gpsd local (JSON sur TCP 2947), utile si le port est partagé ;
- mock   : trajet simulé à partir de la vitesse runtime (mode --mock).
"""

import glob
import json
import math
import socket
import threading
import time

from src.gps.nmea import GpsFix, NmeaParser
from src.services.base_service import BaseService
from src.services.param_types import ServiceParamType

BAUD_CANDIDATES = (4800, 9600, 19200, 38400)
GPSD_MODES = {0: "NO_FIX", 1: "NO_FIX", 2: "2D", 3: "3D"}
EARTH_RADIUS_M = 6371008.8
POSITION_TTL_S = 3.0
RETRY_DELAY_S = 2.0
BAUD_PROBE_S = 2.5


def default_serial_port() -> str:
    """Premier adaptateur USB-série détecté, sinon le port USB par défaut."""
    for pattern in ("/dev/serial/by-id/*", "/dev/ttyUSB*", "/dev/ttyACM*"):
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[0]
    return "/dev/ttyUSB0"


def destination_point(lat: float, lon: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    """Point atteint depuis (lat, lon) après distance_m au cap bearing_deg."""
    delta = distance_m / EARTH_RADIUS_M
    theta = math.radians(bearing_deg)
    phi1 = math.radians(lat)
    lambda1 = math.radians(lon)
    phi2 = math.asin(math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta))
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(phi2), (math.degrees(lambda2) + 540.0) % 360.0 - 180.0


class GpsService(BaseService):
    def __init__(self, runtime, storage=None, *, mock=False):
        super().__init__(
            "GPS",
            storage,
            service_id="clios.gps",
            description="Position et cap GPS temps réel (NMEA série ou gpsd)",
        )
        self.runtime = runtime
        self.mock = mock
        self._thread = None
        self._parser = NmeaParser()
        self._source_label = ""
        self._heading = 0.0
        self._heading_valid = False
        self._last_publish = 0.0
        self._reconnect = threading.Event()

        self.register_param("source", "Source", ServiceParamType.LIST, "auto",
                            options=["auto", "serial", "gpsd"])
        self.register_param("port", "Port série", ServiceParamType.TEXT, "")
        self.register_param("baud", "Débit série", ServiceParamType.LIST, "auto",
                            options=["auto"] + [str(rate) for rate in BAUD_CANDIDATES])
        self.register_param("gpsd_host", "Hôte gpsd", ServiceParamType.TEXT, "127.0.0.1:2947")
        self.register_param("heading_min_speed", "Vitesse mini cap (km/h)", ServiceParamType.SLIDER, 3.0,
                            min_val=0.0, max_val=20.0)
        self.register_param("tile_url", "Serveur de tuiles (%z/%x/%y)", ServiceParamType.TEXT,
                            "https://tile.openstreetmap.org/%z/%x/%y.png")
        self.register_param("mock_origin", "Origine simulation (lat,lon)", ServiceParamType.TEXT,
                            "48.8584,2.2945")

    # ------------------------------------------------------------------ cycle
    def start(self, stop_event: threading.Event):
        self._thread = threading.Thread(target=self._run, args=(stop_event,), daemon=True, name="GpsWorker")
        self._thread.start()
        super().start(stop_event, implemented=True)

    def on_param_changed(self, key, value):
        if key in ("source", "port", "baud", "gpsd_host"):
            self._reconnect.set()
        if key == "tile_url":
            self._publish_config()

    def _param(self, key):
        return self._params[key]["value"]

    def _run(self, stop_event: threading.Event):
        self._publish_config()
        while not stop_event.is_set():
            self._reconnect.clear()
            self._parser = NmeaParser()
            try:
                if self.mock:
                    self._run_mock(stop_event)
                else:
                    source = self._param("source")
                    if source == "gpsd":
                        self._run_gpsd(stop_event)
                    elif source == "serial":
                        self._run_serial(stop_event)
                    else:
                        try:
                            self._run_serial(stop_event)
                        except OSError as serial_error:
                            try:
                                self._run_gpsd(stop_event)
                            except OSError as gpsd_error:
                                raise OSError(f"série : {serial_error} ; gpsd : {gpsd_error}") from gpsd_error
            except (OSError, ValueError) as exc:
                self._publish_lost()
                self.set_error(f"GPS indisponible : {exc}")
            if not self._reconnect.is_set():
                stop_event.wait(RETRY_DELAY_S)

    def _should_stop(self, stop_event):
        return stop_event.is_set() or self._reconnect.is_set()

    # ---------------------------------------------------------------- serial
    def _run_serial(self, stop_event):
        try:
            import serial
        except ImportError as exc:
            raise OSError("pyserial absent") from exc
        port = self._param("port") or default_serial_port()
        baud = self._param("baud")
        rates = BAUD_CANDIDATES if baud == "auto" else (int(baud),)
        for rate in rates:
            if self._should_stop(stop_event):
                return
            try:
                link = serial.Serial(port, rate, timeout=1.0)
            except serial.SerialException as exc:
                raise OSError(str(exc)) from exc
            with link:
                if not self._probe(link, stop_event):
                    continue
                self._source_label = f"serial:{port}@{rate}"
                self.set_ok(f"Récepteur NMEA sur {port} ({rate} bauds)")
                self._read_serial(link, stop_event)
                return
        raise OSError(f"aucune trame NMEA valide sur {port}")

    def _probe(self, link, stop_event) -> bool:
        deadline = time.monotonic() + BAUD_PROBE_S
        while time.monotonic() < deadline and not self._should_stop(stop_event):
            line = link.readline().decode("ascii", errors="replace")
            if self._parser.feed(line):
                return True
        return False

    def _read_serial(self, link, stop_event):
        silent_since = time.monotonic()
        while not self._should_stop(stop_event):
            try:
                raw = link.readline()
            except Exception as exc:  # pyserial lève SerialException à la déconnexion
                raise OSError(f"lecture série : {exc}") from exc
            if raw:
                silent_since = time.monotonic()
                self.ingest_nmea(raw.decode("ascii", errors="replace"))
            elif time.monotonic() - silent_since > POSITION_TTL_S:
                self._publish_lost()
                self.set_warning("Récepteur GPS muet")

    def ingest_nmea(self, line: str):
        """Traite une ligne NMEA et publie à chaque fin d'époque (RMC/GGA)."""
        kind = self._parser.feed(line)
        if kind in ("RMC", "GGA"):
            self._publish_fix(self._parser.fix)

    # ------------------------------------------------------------------ gpsd
    def _run_gpsd(self, stop_event):
        host, _, port = self._param("gpsd_host").partition(":")
        with socket.create_connection((host or "127.0.0.1", int(port or 2947)), timeout=5.0) as conn:
            conn.sendall(b'?WATCH={"enable":true,"json":true};\n')
            conn.settimeout(1.0)
            self._source_label = f"gpsd:{host}"
            self.set_ok(f"Connecté à gpsd ({self._param('gpsd_host')})")
            buffer = b""
            silent_since = time.monotonic()
            while not self._should_stop(stop_event):
                try:
                    chunk = conn.recv(4096)
                except socket.timeout:
                    chunk = None
                if chunk == b"":
                    raise OSError("gpsd a fermé la connexion")
                if chunk:
                    silent_since = time.monotonic()
                    buffer += chunk
                    *lines, buffer = buffer.split(b"\n")
                    for line in lines:
                        try:
                            self.ingest_gpsd(json.loads(line))
                        except (ValueError, TypeError):
                            continue
                elif time.monotonic() - silent_since > POSITION_TTL_S:
                    self._publish_lost()

    def ingest_gpsd(self, message: dict):
        fix = self._parser.fix
        kind = message.get("class")
        if kind == "SKY":
            satellites = message.get("satellites") or []
            fix.satellites_in_view = len(satellites)
            fix.satellites_used = sum(1 for sat in satellites if sat.get("used"))
            if message.get("hdop") is not None:
                fix.hdop = float(message["hdop"])
        elif kind == "TPV":
            mode = int(message.get("mode", 0))
            fix.mode = GPSD_MODES.get(mode, "NO_FIX")
            fix.valid = mode >= 2 and "lat" in message and "lon" in message
            fix.quality = "GPS" if fix.valid else "NONE"
            if fix.valid:
                fix.latitude = float(message["lat"])
                fix.longitude = float(message["lon"])
            if message.get("altMSL", message.get("alt")) is not None:
                fix.altitude_m = float(message.get("altMSL", message.get("alt")))
            if message.get("speed") is not None:
                fix.speed_kmh = float(message["speed"]) * 3.6
            if message.get("track") is not None:
                fix.course_deg = float(message["track"]) % 360.0
            if message.get("eph") is not None:
                fix.accuracy_m = float(message["eph"])
            fix.utc_time = str(message.get("time", ""))
            self._publish_fix(fix)

    # ------------------------------------------------------------------ mock
    def _run_mock(self, stop_event):
        try:
            lat_text, lon_text = self._param("mock_origin").split(",")
            lat, lon = float(lat_text), float(lon_text)
        except ValueError:
            lat, lon = 48.8584, 2.2945
        heading = 90.0
        radius_m = 350.0
        self._source_label = "mock"
        self.set_ok("GPS simulé")
        last = time.monotonic()
        while not self._should_stop(stop_event):
            stop_event.wait(0.2)
            now = time.monotonic()
            dt, last = now - last, now
            speed = float(self.runtime.snapshot().domain("motion").get("speed", 0.0) or 0.0)
            distance = speed / 3.6 * dt
            heading = (heading + math.degrees(distance / radius_m)) % 360.0
            lat, lon = destination_point(lat, lon, heading, distance)
            self._publish_fix(GpsFix(
                latitude=lat, longitude=lon, altitude_m=35.0, speed_kmh=speed,
                course_deg=heading, valid=True, quality="SIMULATION", mode="3D",
                satellites_used=9, satellites_in_view=12, hdop=0.9, accuracy_m=3.0,
            ))

    # ----------------------------------------------------------- publication
    def _publish_fix(self, fix: GpsFix):
        has_position = fix.valid and fix.latitude is not None and fix.longitude is not None
        speed = fix.speed_kmh or 0.0
        # Le cap GPS (route fond) n'a de sens qu'en mouvement : on garde le
        # dernier cap connu à l'arrêt pour éviter une flèche qui tourne.
        if has_position and fix.course_deg is not None and speed >= self._param("heading_min_speed"):
            self._heading = fix.course_deg
            self._heading_valid = True
        elif speed < self._param("heading_min_speed"):
            self._heading_valid = False

        values = {
            "gps_fix": has_position,
            "gps_mode": fix.mode if has_position else "NO_FIX",
            "gps_quality": fix.quality,
            "gps_satellites": fix.satellites_used,
            "gps_satellites_in_view": fix.satellites_in_view,
            "gps_source": self._source_label,
            "heading": round(self._heading, 1),
            "heading_valid": self._heading_valid,
        }
        if fix.hdop is not None:
            values["gps_hdop"] = fix.hdop
        if fix.accuracy_m is not None:
            values["gps_accuracy_m"] = fix.accuracy_m
        if has_position:
            values.update({
                "latitude": round(fix.latitude, 7),
                "longitude": round(fix.longitude, 7),
                "gps_speed": round(speed, 1),
            })
            if fix.altitude_m is not None:
                values["altitude_m"] = round(fix.altitude_m, 1)
        self.runtime.publish(
            "navigation", values, source="gps", ttl_s=POSITION_TTL_S,
            units={"latitude": "deg", "longitude": "deg", "gps_speed": "km/h",
                   "heading": "deg", "altitude_m": "m", "gps_accuracy_m": "m"},
        )
        self._last_publish = time.monotonic()
        if not has_position and self.status.value == "OK":
            self.set_warning(f"Recherche satellites ({fix.satellites_in_view} visibles)")
        elif has_position and self.status.value != "OK":
            self.set_ok(f"Fix {fix.mode} — {fix.satellites_used} satellites")

    def _publish_lost(self):
        self.runtime.publish("navigation", {"gps_fix": False, "gps_mode": "NO_FIX"},
                             source="gps", ttl_s=None)

    def _publish_config(self):
        self.runtime.publish("navigation", {"tile_url": self._param("tile_url")},
                             source="gps-config", ttl_s=None)
