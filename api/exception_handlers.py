import logging

from rest_framework.views import exception_handler

logger = logging.getLogger("api.audit")


def safe_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response

    request = context.get("request") if isinstance(context, dict) else None
    logger.exception(
        "unhandled_api_exception path=%s method=%s exc=%s",
        getattr(request, "path", None),
        getattr(request, "method", None),
        exc.__class__.__name__,
    )
    return None
