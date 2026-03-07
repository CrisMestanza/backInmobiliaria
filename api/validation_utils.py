import math
import re

from api.models import Inmobiliaria


PHONE_DIGIT_RE = re.compile(r"\D")


def normalize_phone(value):
    digits = PHONE_DIGIT_RE.sub("", (value or "").strip())
    # Normaliza variaciones comunes de Peru: +51XXXXXXXXX, 51XXXXXXXXX, 0XXXXXXXXX
    if digits.startswith("51") and len(digits) > 9:
        digits = digits[-9:]
    if digits.startswith("0") and len(digits) > 9:
        digits = digits[-9:]
    return digits


def inmobiliaria_phone_exists_normalized(phone_digits, exclude_id=None):
    if not phone_digits:
        return False
    qs = Inmobiliaria.objects.all().only("idinmobiliaria", "telefono")
    if exclude_id is not None:
        qs = qs.exclude(idinmobiliaria=exclude_id)
    for inmo in qs:
        if normalize_phone(getattr(inmo, "telefono", "")) == phone_digits:
            return True
    return False


def parse_polygon_points(raw_points):
    points = []
    if not isinstance(raw_points, list):
        return points

    for p in raw_points:
        if not isinstance(p, dict):
            continue
        lat = p.get("latitud", p.get("lat"))
        lng = p.get("longitud", p.get("lng"))
        try:
            latf = float(lat)
            lngf = float(lng)
        except (TypeError, ValueError):
            continue
        if not (-90 <= latf <= 90 and -180 <= lngf <= 180):
            continue
        points.append({"latitud": latf, "longitud": lngf})
    return points


def polygon_area_m2(points):
    # Aproximación equirectangular para validar tamaños extremos.
    if len(points) < 3:
        return 0.0
    earth_radius = 6371000.0
    mean_lat = math.radians(sum(p["latitud"] for p in points) / len(points))
    xy = []
    for p in points:
        lat_rad = math.radians(p["latitud"])
        lng_rad = math.radians(p["longitud"])
        x = earth_radius * lng_rad * math.cos(mean_lat)
        y = earth_radius * lat_rad
        xy.append((x, y))

    area2 = 0.0
    for i in range(len(xy)):
        x1, y1 = xy[i]
        x2, y2 = xy[(i + 1) % len(xy)]
        area2 += (x1 * y2) - (x2 * y1)
    return abs(area2) / 2.0
