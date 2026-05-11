from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.error_reporting import notify_frontend_report
from api.throttling import FrontendErrorReportThrottle


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([FrontendErrorReportThrottle])
def frontend_error_report(request):
    request._skip_error_reporting = True
    payload = request.data if isinstance(request.data, dict) else {"payload": request.data}
    notify_frontend_report(request, payload)
    return Response({"ok": True}, status=status.HTTP_202_ACCEPTED)
