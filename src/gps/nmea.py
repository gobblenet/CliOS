"""Décodage NMEA 0183 pour récepteurs GPS série (Garmin GPS 17x HVS, etc.).

Le parseur est volontairement sans dépendance : il valide le checksum,
reconnaît les talkers GP/GN/GL/GA/BD et accumule les phrases utiles
(RMC, GGA, VTG, GSA, GSV, Garmin PGRME) dans un état de position unique.
"""

from __future__ import annotations

from dataclasses import dataclass, field

KNOTS_TO_KMH = 1.852

# Qualité GGA → libellé court exposé à l'UI.
FIX_QUALITY = {
    0: "NONE", 1: "GPS", 2: "DGPS", 3: "PPS", 4: "RTK",
    5: "RTK_FLOAT", 6: "ESTIMATED", 7: "MANUAL", 8: "SIMULATION",
}


def checksum(body: str) -> str:
    value = 0
    for char in body:
        value ^= ord(char)
    return f"{value:02X}"


def split_sentence(line: str) -> list[str] | None:
    """Retourne les champs d'une phrase valide, ou None si invalide.

    Une phrase sans checksum est refusée : les récepteurs Garmin en émettent
    toujours un, et une ligne tronquée ne doit jamais déplacer le véhicule.
    """
    line = line.strip()
    if not line.startswith("$") or "*" not in line:
        return None
    body, _, given = line[1:].rpartition("*")
    if len(given) < 2 or checksum(body) != given[:2].upper():
        return None
    return body.split(",")


def _float(value: str) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _int(value: str) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None


def parse_coordinate(value: str, hemisphere: str) -> float | None:
    """Convertit ddmm.mmmm / dddmm.mmmm + hémisphère en degrés décimaux."""
    if not value or not hemisphere or "." not in value:
        return None
    try:
        dot = value.index(".")
        degrees = float(value[:dot - 2])
        minutes = float(value[dot - 2:])
    except ValueError:
        return None
    if minutes >= 60.0:
        return None
    result = degrees + minutes / 60.0
    if hemisphere in ("S", "W"):
        result = -result
    elif hemisphere not in ("N", "E"):
        return None
    return result


@dataclass
class GpsFix:
    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = None
    speed_kmh: float | None = None
    course_deg: float | None = None
    valid: bool = False
    quality: str = "NONE"
    mode: str = "NO_FIX"
    satellites_used: int = 0
    satellites_in_view: int = 0
    hdop: float | None = None
    accuracy_m: float | None = None
    utc_time: str = ""
    utc_date: str = ""
    sentences: int = 0
    rejected: int = 0
    _gsv_pending: int = field(default=0, repr=False)


class NmeaParser:
    """Accumule les phrases NMEA dans un GpsFix cohérent."""

    def __init__(self):
        self.fix = GpsFix()

    def feed(self, line: str) -> str | None:
        """Traite une ligne. Retourne le type de phrase reconnu (ex. "RMC")."""
        fields = split_sentence(line)
        if fields is None:
            if line.strip():
                self.fix.rejected += 1
            return None
        address = fields[0]
        if address.startswith("P"):
            kind = address  # Phrase propriétaire : PGRME, PGRMT...
        elif len(address) == 5:
            kind = address[2:]
        else:
            return None
        handler = getattr(self, f"_on_{kind.lower()}", None)
        if handler is None:
            return None
        try:
            handler(fields)
        except IndexError:
            self.fix.rejected += 1
            return None
        self.fix.sentences += 1
        return kind

    def _on_rmc(self, f: list[str]):
        # $GPRMC,hhmmss,A,llll.ll,a,yyyyy.yy,a,x.x,x.x,ddmmyy,x.x,a*hh
        fix = self.fix
        fix.utc_time = f[1]
        fix.utc_date = f[9]
        fix.valid = f[2] == "A"
        if not fix.valid:
            return
        lat = parse_coordinate(f[3], f[4])
        lon = parse_coordinate(f[5], f[6])
        if lat is not None and lon is not None:
            fix.latitude, fix.longitude = lat, lon
        knots = _float(f[7])
        if knots is not None:
            fix.speed_kmh = knots * KNOTS_TO_KMH
        course = _float(f[8])
        if course is not None:
            fix.course_deg = course % 360.0

    def _on_gga(self, f: list[str]):
        # $GPGGA,hhmmss,llll.ll,a,yyyyy.yy,a,q,ss,h.h,alt,M,...
        fix = self.fix
        quality = _int(f[6]) or 0
        fix.quality = FIX_QUALITY.get(quality, "NONE")
        fix.satellites_used = _int(f[7]) or 0
        fix.hdop = _float(f[8])
        if quality == 0:
            return
        lat = parse_coordinate(f[2], f[3])
        lon = parse_coordinate(f[4], f[5])
        if lat is not None and lon is not None:
            fix.latitude, fix.longitude = lat, lon
        altitude = _float(f[9])
        if altitude is not None:
            fix.altitude_m = altitude

    def _on_vtg(self, f: list[str]):
        # $GPVTG,cog,T,cog,M,knots,N,kmh,K*hh
        course = _float(f[1])
        if course is not None:
            self.fix.course_deg = course % 360.0
        kmh = _float(f[7])
        if kmh is not None:
            self.fix.speed_kmh = kmh

    def _on_gsa(self, f: list[str]):
        self.fix.mode = {"1": "NO_FIX", "2": "2D", "3": "3D"}.get(f[2], "NO_FIX")

    def _on_gsv(self, f: list[str]):
        total = _int(f[3])
        if total is not None:
            self.fix.satellites_in_view = total

    def _on_pgrme(self, f: list[str]):
        # Garmin : $PGRME,hpe,M,vpe,M,epe,M*hh (erreur horizontale estimée).
        hpe = _float(f[1])
        if hpe is not None:
            self.fix.accuracy_m = hpe
