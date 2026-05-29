from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.security.conf import get_security_config


@api_view(["GET"])
@permission_classes([AllowAny])
def waf_health(request):
    config = get_security_config()
    return Response(
        {
            "ok": True,
            "waf_enabled": config.enabled,
            "waf_version": config.version,
        }
    )
