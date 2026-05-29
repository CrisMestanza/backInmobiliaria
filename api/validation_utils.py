import math
import re
from urllib.parse import urlparse

from django.conf import settings

from api.models import Inmobiliaria


PHONE_DIGIT_RE = re.compile(r"\D")
HTML_TAG_RE = re.compile(r"<[^>]+>")
SCRIPTISH_RE = re.compile(
    r"(?i)(<\s*script|javascript:|onerror\s*=|onload\s*=|data:text/html|<\s*iframe|<\s*object|<\s*embed)"
)
URL_RE = re.compile(r"(?i)\bhttps?://|www\.")
LETTER_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]")
NAME_PART_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}")
REPEATED_CHARS_RE = re.compile(r"(.)\1{5,}")
DISPOSABLE_EMAIL_DOMAINS = {
    "10minutemail.com",
    "20minutemail.com",
    "guerrillamail.com",
    "mailinator.com",
    "tempmail.com",
    "temp-mail.org",
    "yopmail.com",
    "noyavip.com",
    "lohinja.com",
    "pazard.com",
}
SUSPICIOUS_EMAIL_DOMAIN_TOKENS = (
    "tempmail",
    "mailinator",
    "guerrillamail",
    "throwaway",
    "disposable",
)


def normalize_phone(value):
    digits = PHONE_DIGIT_RE.sub("", (value or "").strip())
    # Normaliza variaciones comunes de Peru: +51XXXXXXXXX, 51XXXXXXXXX, 0XXXXXXXXX
    if digits.startswith("51") and len(digits) > 9:
        digits = digits[-9:]
    if digits.startswith("0") and len(digits) > 9:
        digits = digits[-9:]
    return digits


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def contains_unsafe_markup(value):
    text = str(value or "")
    return bool(SCRIPTISH_RE.search(text) or HTML_TAG_RE.search(text))


def looks_like_url(value):
    return bool(URL_RE.search(str(value or "")))


def has_repeated_junk(value):
    return bool(REPEATED_CHARS_RE.search(str(value or "")))


def email_domain(value):
    email = str(value or "").strip().lower()
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1]


def is_disposable_email(value):
    domain = email_domain(value)
    if not domain:
        return False
    return domain in DISPOSABLE_EMAIL_DOMAINS or any(token in domain for token in SUSPICIOUS_EMAIL_DOMAIN_TOKENS)


def is_unapproved_internal_email(value):
    email = str(value or "").strip().lower()
    domain = email_domain(email)
    reserved_domains = set(getattr(settings, "REGISTRATION_RESERVED_EMAIL_DOMAINS", ("geohabita.com",)) or ())
    allowed_emails = {
        str(item).strip().lower()
        for item in getattr(settings, "REGISTRATION_ALLOWED_INTERNAL_EMAILS", ()) or ()
        if str(item).strip()
    }
    return domain in reserved_domains and email not in allowed_emails


def is_realistic_person_name(value):
    name = normalize_text(value)
    if len(name) < 5 or len(name) > 80:
        return False
    if contains_unsafe_markup(name) or looks_like_url(name) or has_repeated_junk(name):
        return False
    return len(NAME_PART_RE.findall(name)) >= 2


def is_reasonable_business_name(value):
    name = normalize_text(value)
    if len(name) < 3 or len(name) > 100:
        return False
    if contains_unsafe_markup(name) or looks_like_url(name) or has_repeated_junk(name):
        return False
    return len(LETTER_RE.findall(name)) >= 3


def is_reasonable_description(value, *, min_len=10, max_len=450):
    text = normalize_text(value)
    if len(text) < min_len or len(text) > max_len:
        return False
    if contains_unsafe_markup(text) or has_repeated_junk(text):
        return False
    return len(LETTER_RE.findall(text)) >= min(6, min_len)


def normalize_social_url(value, *, platform):
    text = normalize_text(value)
    if not text:
        return ""
    if contains_unsafe_markup(text):
        raise ValueError("No se permite HTML o scripts.")
    if text.startswith("@"):
        text = text[1:]
    if platform == "facebook":
        if text.startswith("http://") or text.startswith("https://"):
            parsed = urlparse(text)
            host = (parsed.netloc or "").lower()
            if host not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
                raise ValueError("Ingresa un enlace valido de Facebook.")
            if "facebook.com/" in (parsed.path or "").lower():
                raise ValueError("El enlace de Facebook no es valido.")
            return text
        if "/" in text or "." in text:
            raise ValueError("Ingresa un usuario de Facebook o una URL valida.")
        return f"https://www.facebook.com/{text}"
    if platform == "tiktok":
        if text.startswith("http://") or text.startswith("https://"):
            parsed = urlparse(text)
            host = (parsed.netloc or "").lower()
            if host not in {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}:
                raise ValueError("Ingresa un enlace valido de TikTok.")
            return text
        if "/" in text or "." in text:
            raise ValueError("Ingresa un usuario de TikTok o una URL valida.")
        return text
    return text


def normalize_website_url(value):
    text = normalize_text(value)
    if not text:
        return ""
    if contains_unsafe_markup(text):
        raise ValueError("No se permite HTML o scripts.")
    if not text.startswith(("http://", "https://")):
        text = f"https://{text}"
    parsed = urlparse(text)
    host = (parsed.netloc or "").lower()
    if not host or "." not in host or host in {"localhost", "example.com"}:
        raise ValueError("Ingresa una pagina web valida.")
    return text


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
