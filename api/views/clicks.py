from django.core.cache import cache
from django.db.models import Case, Count, IntegerField, Min, Max, OuterRef, Q, Subquery, Sum, Value, When
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.authentication import CustomJWTAuthentication
from api.dashboard_cache import (
    invalidate_dashboard_cache_for_inmobiliaria,
    lotes_cache_key,
    overview_cache_key,
    register_lotes_cache_key,
)
from api.models import ClickProyectos, ClicksContactos, Espacio, ImagenesProyecto, Lote, Proyecto
from api.serializers import ClickProyectosSerializer, ClicksContactosSerializer
from api.throttling import ClickRateThrottle
from api.views.permissions import user_inmobiliaria_id


def _dashboard_permission_error(request, idinmobiliaria):
    owner_inmo_id = user_inmobiliaria_id(request.user)
    if not owner_inmo_id or int(idinmobiliaria) != int(owner_inmo_id):
        return None, Response(
            {"error": "No tienes permisos para ver este dashboard."}, status=403
        )
    return owner_inmo_id, None


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ClickRateThrottle])
def registerClickProyecto(request):
    data = {
        "idproyecto": request.data.get("idproyecto"),
        "fecha": request.data.get("fecha"),
        "hora": request.data.get("hora"),
        "click": 1,
    }
    serializer = ClickProyectosSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ClickRateThrottle])
def registerClickContactos(request):
    data = {
        "idproyecto": request.data.get("idproyecto"),
        "dia": request.data.get("dia"),
        "hora": request.data.get("hora"),
        "click": 1,
        "redSocial": request.data.get("redSocial"),
    }
    serializer = ClicksContactosSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def dashboard_clicks_inmobiliaria(request, idinmobiliaria):
    try:
        owner_inmo_id, error_response = _dashboard_permission_error(
            request, idinmobiliaria
        )
        if error_response:
            return error_response

        # 🔹 Obtener los proyectos de la inmobiliaria
        proyectos = Proyecto.objects.filter(idinmobiliaria=idinmobiliaria)
        if not proyectos.exists():
            return Response(
                {
                    "total_clicks_contactos": 0,
                    "total_clicks_proyectos": 0,
                    "detalle_contactos": [],
                }
            )

        # 🧩 Total de clics en Contactos
        total_clicks_contactos = (
            ClicksContactos.objects.filter(idproyecto__in=proyectos)
            .aggregate(total=Sum("click"))
            .get("total")
            or 0
        )

        # 🧩 Total de clics en Proyectos
        total_clicks_proyectos = (
            ClickProyectos.objects.filter(idproyecto__in=proyectos)
            .aggregate(total=Sum("click"))
            .get("total")
            or 0
        )

        # 🧩 Detalle por redSocial
        detalle_contactos = (
            ClicksContactos.objects.filter(idproyecto__in=proyectos)
            .values("redSocial")
            .annotate(total=Sum("click"))
        )

        # 🔹 Armar respuesta
        return Response(
            {
                "total_clicks_contactos": total_clicks_contactos,
                "total_clicks_proyectos": total_clicks_proyectos,
                "detalle_contactos": list(detalle_contactos),
            }
        )

    except Exception:
        return Response({"error": "No se pudo obtener la información solicitada."}, status=500)


@api_view(["GET"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def dashboard_overview_inmobiliaria(request, idinmobiliaria):
    try:
        _owner_inmo_id, error_response = _dashboard_permission_error(
            request, idinmobiliaria
        )
        if error_response:
            return error_response

        cache_key = overview_cache_key(idinmobiliaria)
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        hero_image_subquery = ImagenesProyecto.objects.filter(
            idproyecto=OuterRef("pk")
        ).order_by("idimagenesp")

        proyectos_qs = (
            Proyecto.objects.filter(idinmobiliaria=idinmobiliaria)
            .annotate(
                hero_image=Subquery(hero_image_subquery.values("imagenproyecto")[:1])
            )
            .values(
                "idproyecto",
                "nombreproyecto",
                "latitud",
                "longitud",
                "publico_mapa",
                "estado",
                "idtipoinmobiliaria",
                "precio",
                "moneda",
                "financing_config",
                "hero_image",
            )
        )
        proyectos = list(proyectos_qs)
        proyecto_ids = [p["idproyecto"] for p in proyectos]

        resumen = {
            "proyectosActivos": len(proyectos),
            "totalLotes": 0,
            "lotesDisponibles": 0,
            "lotesReservados": 0,
            "lotesVendidos": 0,
            "totalEspacios": 0,
            "areaEspacios": 0,
        }
        clicks = {
            "total_clicks_contactos": 0,
            "total_clicks_proyectos": 0,
            "detalle_contactos": [],
        }
        latest_lotes = []

        if proyecto_ids:
            resumen = (
                Lote.objects.filter(idproyecto__in=proyecto_ids)
                .aggregate(
                    totalLotes=Count("idlote"),
                    lotesDisponibles=Count(
                        Case(When(vendido=0, then=1), output_field=IntegerField())
                    ),
                    lotesReservados=Count(
                        Case(When(vendido=2, then=1), output_field=IntegerField())
                    ),
                    lotesVendidos=Count(
                        Case(When(vendido=1, then=1), output_field=IntegerField())
                    ),
                )
            )
            resumen["proyectosActivos"] = len(proyectos)
            espacios_resumen = Espacio.objects.filter(
                idproyecto__in=proyecto_ids,
                estado=1,
            ).aggregate(
                totalEspacios=Count("idespacio"),
                areaEspacios=Sum("area_m2"),
            )
            resumen["totalEspacios"] = espacios_resumen.get("totalEspacios") or 0
            resumen["areaEspacios"] = float(espacios_resumen.get("areaEspacios") or 0)

            lotes_stats = {
                row["idproyecto"]: row
                for row in Lote.objects.filter(idproyecto__in=proyecto_ids)
                .values("idproyecto")
                .annotate(
                    total=Count("idlote"),
                    disponible=Count(
                        Case(When(vendido=0, then=1), output_field=IntegerField())
                    ),
                    reservado=Count(
                        Case(When(vendido=2, then=1), output_field=IntegerField())
                    ),
                    vendido=Count(
                        Case(When(vendido=1, then=1), output_field=IntegerField())
                    ),
                    precio_min=Min("precio"),
                    precio_max=Max("precio"),
                )
            }
            espacios_stats = {
                row["idproyecto"]: row
                for row in Espacio.objects.filter(idproyecto__in=proyecto_ids, estado=1)
                .values("idproyecto")
                .annotate(
                    total=Count("idespacio"),
                    visibles=Count(
                        Case(When(visible_mapa=1, then=1), output_field=IntegerField())
                    ),
                    destacados=Count(
                        Case(When(destacado=1, then=1), output_field=IntegerField())
                    ),
                    area_total=Sum("area_m2"),
                )
            }
            espacios_tipo_rows = list(
                Espacio.objects.filter(idproyecto__in=proyecto_ids, estado=1)
                .values("idproyecto", "idtipoespacio__nombre")
                .annotate(total=Count("idespacio"))
                .order_by("idproyecto", "-total", "idtipoespacio__nombre")
            )
            espacios_tipos_por_proyecto = {}
            for row in espacios_tipo_rows:
                bucket = espacios_tipos_por_proyecto.setdefault(row["idproyecto"], [])
                if len(bucket) >= 3:
                    continue
                bucket.append(
                    {
                        "nombre": row.get("idtipoespacio__nombre") or "Espacio",
                        "total": row.get("total") or 0,
                    }
                )
            clicks_proyecto = {
                row["idproyecto"]: row["total"] or 0
                for row in ClickProyectos.objects.filter(idproyecto__in=proyecto_ids)
                .values("idproyecto")
                .annotate(total=Sum("click"))
            }
            contactos_proyecto = {
                row["idproyecto"]: row["total"] or 0
                for row in ClicksContactos.objects.filter(idproyecto__in=proyecto_ids)
                .values("idproyecto")
                .annotate(total=Sum("click"))
            }
            detalle_contactos = list(
                ClicksContactos.objects.filter(idproyecto__in=proyecto_ids)
                .values("redSocial")
                .annotate(total=Sum("click"))
            )
            total_clicks_contactos = sum(contactos_proyecto.values())
            total_clicks_proyectos = sum(clicks_proyecto.values())
            clicks = {
                "total_clicks_contactos": total_clicks_contactos,
                "total_clicks_proyectos": total_clicks_proyectos,
                "detalle_contactos": detalle_contactos,
            }
            latest_lotes = list(
                Lote.objects.filter(idproyecto__in=proyecto_ids)
                .select_related("idproyecto")
                .order_by("-idlote")
                .values(
                    "idlote",
                    "nombre",
                    "descripcion",
                    "precio",
                    "vendido",
                    "area_total_m2",
                    "idproyecto",
                    "idproyecto__nombreproyecto",
                )[:8]
            )

            for proyecto in proyectos:
                stats = lotes_stats.get(proyecto["idproyecto"], {})
                proyecto["lote_stats"] = {
                    "total": stats.get("total", 0),
                    "disponible": stats.get("disponible", 0),
                    "reservado": stats.get("reservado", 0),
                    "vendido": stats.get("vendido", 0),
                    "precio_min": stats.get("precio_min"),
                    "precio_max": stats.get("precio_max"),
                }
                espacio_stats = espacios_stats.get(proyecto["idproyecto"], {})
                proyecto["space_stats"] = {
                    "total": espacio_stats.get("total", 0),
                    "visibles": espacio_stats.get("visibles", 0),
                    "destacados": espacio_stats.get("destacados", 0),
                    "area_total": float(espacio_stats.get("area_total") or 0),
                    "top_types": espacios_tipos_por_proyecto.get(
                        proyecto["idproyecto"], []
                    ),
                }
                proyecto["total_clicks"] = clicks_proyecto.get(
                    proyecto["idproyecto"], 0
                )
                proyecto["total_contactos"] = contactos_proyecto.get(
                    proyecto["idproyecto"], 0
                )

        payload = {
            "resumen": resumen,
            "clicks": clicks,
            "proyectos": proyectos,
            "latest_lotes": latest_lotes,
        }
        cache.set(cache_key, payload, timeout=60)
        return Response(payload)
    except Exception:
        return Response({"error": "No se pudo obtener la información solicitada."}, status=500)


@api_view(["GET"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def dashboard_lotes_inmobiliaria(request, idinmobiliaria):
    try:
        _owner_inmo_id, error_response = _dashboard_permission_error(
            request, idinmobiliaria
        )
        if error_response:
            return error_response

        page = max(1, int(request.GET.get("page", 1)))
        page_size = min(100, max(1, int(request.GET.get("page_size", 20))))
        search = (request.GET.get("search") or "").strip()
        status_filter = request.GET.get("status") or "all"
        project_filter = request.GET.get("project") or "all"
        sort = request.GET.get("sort") or "nombre"
        price_min = request.GET.get("price_min")
        price_max = request.GET.get("price_max")
        area_min = request.GET.get("area_min")
        area_max = request.GET.get("area_max")

        query_string = request.META.get("QUERY_STRING", "")
        cache_key = lotes_cache_key(idinmobiliaria, query_string)
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        lotes_qs = Lote.objects.filter(idproyecto__idinmobiliaria=idinmobiliaria).select_related(
            "idproyecto"
        )

        if search:
            lotes_qs = lotes_qs.filter(
                Q(nombre__icontains=search)
                | Q(descripcion__icontains=search)
                | Q(idproyecto__nombreproyecto__icontains=search)
            )
        if status_filter != "all":
            lotes_qs = lotes_qs.filter(vendido=status_filter)
        if project_filter != "all":
            lotes_qs = lotes_qs.filter(idproyecto=project_filter)
        if price_min not in (None, ""):
            lotes_qs = lotes_qs.filter(precio__gte=price_min)
        if price_max not in (None, ""):
            lotes_qs = lotes_qs.filter(precio__lte=price_max)
        if area_min not in (None, ""):
            lotes_qs = lotes_qs.filter(area_total_m2__gte=area_min)
        if area_max not in (None, ""):
            lotes_qs = lotes_qs.filter(area_total_m2__lte=area_max)

        sort_map = {
            "nombre": "nombre",
            "precio-asc": "precio",
            "precio-desc": "-precio",
            "area-asc": "area_total_m2",
            "area-desc": "-area_total_m2",
            "estado": "vendido",
        }
        lotes_qs = lotes_qs.order_by(sort_map.get(sort, "nombre"), "-idlote")

        total = lotes_qs.count()
        start = (page - 1) * page_size
        end = start + page_size
        items = list(
            lotes_qs.values(
                "idlote",
                "nombre",
                "descripcion",
                "precio",
                "vendido",
                "area_total_m2",
                "idproyecto",
                "idproyecto__nombreproyecto",
            )[start:end]
        )
        payload = {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        }
        cache.set(cache_key, payload, timeout=30)
        register_lotes_cache_key(idinmobiliaria, cache_key)
        return Response(payload)
    except Exception:
        return Response({"error": "No se pudo obtener la información solicitada."}, status=500)
