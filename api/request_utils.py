def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first

    real_ip = request.META.get("HTTP_X_REAL_IP", "").strip()
    if real_ip:
        return real_ip

    return (request.META.get("REMOTE_ADDR") or "").strip()
