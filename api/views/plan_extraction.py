import hashlib
import json

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.decorators import throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.authentication import CustomJWTAuthentication
from api.models import PlanoExtraccionCache
from api.plan_extraction import (
    extract_lot_polygons_combined,
)
from api.views.permissions import is_project_owned_by_user
from api.throttling import PlanExtractionRateThrottle


EXTRACTION_VERSION = "v2_geometry_only"


def _build_request_signature(
    *,
    project_id: str,
    overlay_image_bytes: bytes,
    overlay_pdf_bytes: bytes | None,
    project_polygon,
    image_width: int,
    image_height: int,
) -> str:
    polygon_payload = ""
    if project_polygon:
        if isinstance(project_polygon, str):
            polygon_payload = project_polygon
        else:
            polygon_payload = json.dumps(project_polygon, sort_keys=True)

    digest = hashlib.sha256()
    digest.update(str(project_id).encode("utf-8"))
    digest.update(str(image_width).encode("utf-8"))
    digest.update(str(image_height).encode("utf-8"))
    digest.update(EXTRACTION_VERSION.encode("utf-8"))
    digest.update(hashlib.sha256(overlay_image_bytes).hexdigest().encode("utf-8"))
    if overlay_pdf_bytes:
        digest.update(hashlib.sha256(overlay_pdf_bytes).hexdigest().encode("utf-8"))
    digest.update(polygon_payload.encode("utf-8"))
    return digest.hexdigest()


@api_view(["POST"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([PlanExtractionRateThrottle])
def extract_lotes_from_overlay(request):
    project_id = request.data.get("idproyecto")
    if not project_id or not is_project_owned_by_user(project_id, request.user):
        return Response(
            {"error": "No tienes permisos para extraer lotes en este proyecto."},
            status=status.HTTP_403_FORBIDDEN,
        )

    overlay_image = request.FILES.get("overlay_image")
    if not overlay_image:
        return Response(
            {"overlay_image": ["Debes enviar la imagen rasterizada del PDF."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    overlay_pdf = request.FILES.get("overlay_pdf")
    max_upload_bytes = int(getattr(settings, "MAX_PLAN_EXTRACTION_UPLOAD_MB", 15)) * 1024 * 1024
    total_upload_size = int(getattr(overlay_image, "size", 0) or 0) + int(getattr(overlay_pdf, "size", 0) or 0)
    if total_upload_size > max_upload_bytes:
        return Response(
            {"error": "Los archivos enviados exceden el tamaño máximo permitido."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    project_polygon = request.data.get("project_polygon")
    image_width = int(request.data.get("image_width") or 0)
    image_height = int(request.data.get("image_height") or 0)
    force_refresh = str(request.data.get("force_refresh") or "").lower() in {"1", "true", "yes"}
    overlay_image_bytes = overlay_image.read()
    overlay_pdf_bytes = overlay_pdf.read() if overlay_pdf else None
    request_signature = _build_request_signature(
        project_id=str(project_id),
        overlay_image_bytes=overlay_image_bytes,
        overlay_pdf_bytes=overlay_pdf_bytes,
        project_polygon=project_polygon,
        image_width=image_width,
        image_height=image_height,
    )

    if not force_refresh:
        cached = (
            PlanoExtraccionCache.objects.filter(
                request_signature=request_signature,
                status="completed",
            )
            .only("payload")
            .first()
        )
        if cached:
            payload = dict(cached.payload)
            payload.setdefault("debug", {})
            payload["debug"]["cached"] = True
            payload["debug"]["extraction_version"] = EXTRACTION_VERSION
            return Response(payload, status=status.HTTP_200_OK)

    try:
        result = extract_lot_polygons_combined(
            overlay_image_bytes=overlay_image_bytes,
            overlay_pdf_bytes=overlay_pdf_bytes,
            image_width=image_width,
            image_height=image_height,
            project_polygon=project_polygon,
        )
    except ValueError:
        return Response({"error": "El plano enviado no tiene un formato válido."}, status=status.HTTP_400_BAD_REQUEST)
    except RuntimeError:
        return Response({"error": "No se pudo procesar el plano en este momento."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception:
        return Response(
            {"error": "No se pudo extraer lotes del plano."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    result.setdefault("debug", {})
    result["debug"]["cached"] = False
    result["debug"]["extraction_version"] = EXTRACTION_VERSION
    PlanoExtraccionCache.objects.update_or_create(
        request_signature=request_signature,
        defaults={
            "idproyecto_id": project_id,
            "extraction_version": EXTRACTION_VERSION,
            "status": "completed",
            "payload": result,
        },
    )
    return Response(result, status=status.HTTP_200_OK)
