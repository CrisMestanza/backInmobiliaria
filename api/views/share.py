from __future__ import annotations

import io
import os
import textwrap
from typing import Any

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils.html import strip_tags
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from api.models import Imagenes, ImagenesProyecto, Lote, Proyecto

OG_WIDTH = 1200
OG_HEIGHT = 630
DEFAULT_FRONTEND_BASE_URL = "https://www.geohabita.com"
DEFAULT_SITE_NAME = "GeoHabita"
SOCIAL_CRAWLER_TOKENS = (
    "whatsapp",
    "facebookexternalhit",
    "facebot",
    "twitterbot",
    "linkedinbot",
    "slackbot",
    "telegrambot",
    "discordbot",
    "skypeuripreview",
    "googlebot",
)


def _frontend_base_url() -> str:
    return getattr(settings, "SHARE_FRONTEND_BASE_URL", DEFAULT_FRONTEND_BASE_URL).rstrip("/")


def _is_social_crawler(request) -> bool:
    user_agent = str(request.META.get("HTTP_USER_AGENT", "")).lower()
    return any(token in user_agent for token in SOCIAL_CRAWLER_TOKENS)


def _clean_text(value: Any, fallback: str = "") -> str:
    raw = strip_tags(str(value or fallback)).strip()
    return " ".join(raw.split())


def _format_money(value: Any, currency: str = "S/") -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    return f"{currency} {amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)].rstrip()}…"


def _resolve_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(font_name, size)
    except OSError:
        return ImageFont.load_default()


def _resolve_image_file(model_field: Any) -> str | None:
    if not model_field:
        return None
    try:
        file_path = model_field.path
    except Exception:
        file_path = None
    if file_path and os.path.exists(file_path):
        return file_path
    return None


def _project_primary_image(project: Proyecto) -> str | None:
    project_image = (
        ImagenesProyecto.objects.filter(idproyecto=project.idproyecto)
        .exclude(imagenproyecto="")
        .order_by("idimagenesp")
        .first()
    )
    return _resolve_image_file(getattr(project_image, "imagenproyecto", None))


def _lote_primary_image(lote: Lote) -> str | None:
    lote_image = (
        Imagenes.objects.filter(idlote=lote.idlote)
        .exclude(imagen="")
        .order_by("idimagenes")
        .first()
    )
    resolved = _resolve_image_file(getattr(lote_image, "imagen", None))
    if resolved:
        return resolved
    project = getattr(lote, "idproyecto", None)
    if project:
        return _project_primary_image(project)
    return None


def _load_cover_image(image_path: str | None) -> Image.Image:
    canvas = Image.new("RGB", (OG_WIDTH, OG_HEIGHT), "#07120a")
    if not image_path:
        return canvas

    try:
        with Image.open(image_path) as source:
            cover = ImageOps.fit(source.convert("RGB"), (OG_WIDTH, OG_HEIGHT), method=Image.Resampling.LANCZOS)
            return cover
    except Exception:
        return canvas


def _draw_brand_badge(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.rounded_rectangle((x, y, x + 190, y + 52), radius=24, fill=(12, 28, 18, 220))
    draw.text((x + 18, y + 12), DEFAULT_SITE_NAME, font=_resolve_font(24, bold=True), fill="#d7ffe5")


def _draw_multiline(draw: ImageDraw.ImageDraw, text: str, *, x: int, y: int, width: int, font: ImageFont.ImageFont, fill: str, line_spacing: int = 10) -> int:
    lines = textwrap.wrap(text, width=width) or [text]
    top = y
    for line in lines:
        draw.text((x, top), line, font=font, fill=fill)
        bbox = draw.textbbox((x, top), line, font=font)
        top = bbox[3] + line_spacing
    return top


def _build_og_image(
    *,
    title: str,
    subtitle: str,
    price_label: str,
    meta_line: str,
    image_path: str | None,
) -> bytes:
    base = _load_cover_image(image_path)
    blurred = base.filter(ImageFilter.GaussianBlur(18))
    canvas = Image.blend(blurred, base, 0.45).convert("RGBA")

    shadow = Image.new("RGBA", (OG_WIDTH, OG_HEIGHT), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((54, 64, OG_WIDTH - 54, OG_HEIGHT - 64), radius=38, fill=(0, 0, 0, 125))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas.alpha_composite(shadow)

    overlay = Image.new("RGBA", (OG_WIDTH, OG_HEIGHT), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle(
        (60, 72, OG_WIDTH - 60, OG_HEIGHT - 72),
        radius=38,
        fill=(5, 13, 8, 198),
        outline=(79, 214, 132, 72),
        width=2,
    )
    overlay_draw.ellipse((760, -60, 1220, 400), fill=(22, 163, 74, 42))
    overlay_draw.ellipse((-160, 300, 320, 760), fill=(34, 197, 94, 28))
    canvas.alpha_composite(overlay)

    draw = ImageDraw.Draw(canvas)
    _draw_brand_badge(draw, 92, 102)

    kicker_font = _resolve_font(26, bold=True)
    title_font = _resolve_font(60, bold=True)
    body_font = _resolve_font(28)
    price_font = _resolve_font(42, bold=True)
    meta_font = _resolve_font(24)

    draw.text((92, 186), subtitle.upper(), font=kicker_font, fill="#7dffb2")
    bottom_y = _draw_multiline(
        draw,
        _truncate(title, 70),
        x=92,
        y=232,
        width=24,
        font=title_font,
        fill="#ffffff",
        line_spacing=8,
    )

    draw.rounded_rectangle((92, bottom_y + 20, 430, bottom_y + 96), radius=24, fill=(18, 77, 42, 232))
    draw.text((118, bottom_y + 38), price_label, font=price_font, fill="#f4fff7")

    draw.text((92, OG_HEIGHT - 146), _truncate(meta_line, 90), font=body_font, fill="#d1fae5")
    draw.text((92, OG_HEIGHT - 98), "Comparte este inmueble y abre el mapa interactivo de GeoHabita.", font=meta_font, fill="#98b7a3")

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


def _share_context_for_project(request, project: Proyecto) -> dict[str, Any]:
    inmo = getattr(project, "idinmobiliaria", None)
    inmo_id = getattr(inmo, "idinmobiliaria", None)
    frontend_url = f"{_frontend_base_url()}/mapa/{inmo_id}?proyecto={project.idproyecto}"
    share_url = request.build_absolute_uri(f"/share/proyecto/{project.idproyecto}/")
    og_image_url = request.build_absolute_uri(f"/api/og-image/proyecto/{project.idproyecto}/")
    title = _clean_text(project.nombreproyecto, "Proyecto")
    price = _format_money(project.precio, _clean_text(project.moneda, "S/"))
    description = _truncate(
        _clean_text(project.descripcion, "Explora este proyecto en GeoHabita."),
        180,
    )
    return {
        "page_title": f"{title} | {DEFAULT_SITE_NAME}",
        "og_title": f"{title} | {DEFAULT_SITE_NAME}",
        "og_description": description,
        "og_image": og_image_url,
        "og_image_secure_url": og_image_url,
        "canonical_url": share_url,
        "og_url": share_url,
        "redirect_url": frontend_url,
        "site_name": DEFAULT_SITE_NAME,
        "headline": title,
        "price_label": price,
        "eyebrow": "Proyecto",
        "summary": description,
        "image_alt": f"Vista previa de {title} en GeoHabita",
        "auto_redirect": not _is_social_crawler(request),
    }


def _share_context_for_lote(request, lote: Lote) -> dict[str, Any]:
    project = getattr(lote, "idproyecto", None)
    inmo = getattr(project, "idinmobiliaria", None) if project else None
    inmo_id = getattr(inmo, "idinmobiliaria", None)
    project_id = getattr(project, "idproyecto", None)
    frontend_url = (
        f"{_frontend_base_url()}/mapa/{inmo_id}?proyecto={project_id}&lote={lote.idlote}"
    )
    share_url = request.build_absolute_uri(f"/share/lote/{lote.idlote}/")
    og_image_url = request.build_absolute_uri(f"/api/og-image/lote/{lote.idlote}/")
    title = _clean_text(lote.nombre, "Lote")
    project_name = _clean_text(getattr(project, "nombreproyecto", ""), "Proyecto")
    price = _format_money(lote.precio, _clean_text(lote.moneda or getattr(project, "moneda", None), "S/"))
    description = _truncate(
        _clean_text(
            lote.descripcion,
            f"Revisa este lote en {project_name} y abre el mapa interactivo de GeoHabita.",
        ),
        180,
    )
    return {
        "page_title": f"{title} | {project_name} | {DEFAULT_SITE_NAME}",
        "og_title": f"{title} | {project_name}",
        "og_description": description,
        "og_image": og_image_url,
        "og_image_secure_url": og_image_url,
        "canonical_url": share_url,
        "og_url": share_url,
        "redirect_url": frontend_url,
        "site_name": DEFAULT_SITE_NAME,
        "headline": title,
        "price_label": price,
        "eyebrow": project_name,
        "summary": description,
        "image_alt": f"Vista previa de {title} en GeoHabita",
        "auto_redirect": not _is_social_crawler(request),
    }


def _get_project_or_404(idproyecto: int) -> Proyecto:
    project = Proyecto.objects.select_related("idinmobiliaria").filter(idproyecto=idproyecto, estado=1).first()
    if not project:
        raise Http404("Proyecto no encontrado")
    return project


def _get_lote_or_404(idlote: int) -> Lote:
    lote = (
        Lote.objects.select_related("idproyecto__idinmobiliaria")
        .filter(idlote=idlote)
        .first()
    )
    if not lote:
        raise Http404("Lote no encontrado")
    return lote


@api_view(["GET"])
@permission_classes([AllowAny])
def og_image_proyecto(_request, idproyecto: int) -> HttpResponse:
    project = _get_project_or_404(idproyecto)
    image_bytes = _build_og_image(
        title=_clean_text(project.nombreproyecto, "Proyecto"),
        subtitle="Proyecto",
        price_label=_format_money(project.precio, _clean_text(project.moneda, "S/")),
        meta_line=_truncate(_clean_text(project.descripcion, "Explora este proyecto en GeoHabita."), 90),
        image_path=_project_primary_image(project),
    )
    return HttpResponse(image_bytes, content_type="image/png")


@api_view(["GET"])
@permission_classes([AllowAny])
def og_image_lote(_request, idlote: int) -> HttpResponse:
    lote = _get_lote_or_404(idlote)
    project = getattr(lote, "idproyecto", None)
    image_bytes = _build_og_image(
        title=_clean_text(lote.nombre, "Lote"),
        subtitle=_clean_text(getattr(project, "nombreproyecto", None), "Lote"),
        price_label=_format_money(
            lote.precio,
            _clean_text(lote.moneda or getattr(project, "moneda", None), "S/"),
        ),
        meta_line=_truncate(_clean_text(lote.descripcion, "Explora este lote en GeoHabita."), 90),
        image_path=_lote_primary_image(lote),
    )
    return HttpResponse(image_bytes, content_type="image/png")


def share_proyecto(request, idproyecto: int) -> HttpResponse:
    project = _get_project_or_404(idproyecto)
    response = render(
        request,
        "api/share_redirect.html",
        _share_context_for_project(request, project),
    )
    response["Cache-Control"] = "public, max-age=300"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


def share_lote(request, idlote: int) -> HttpResponse:
    lote = _get_lote_or_404(idlote)
    response = render(
        request,
        "api/share_redirect.html",
        _share_context_for_lote(request, lote),
    )
    response["Cache-Control"] = "public, max-age=300"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response
