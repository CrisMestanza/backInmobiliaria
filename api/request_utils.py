import ipaddress

from django.conf import settings


def _ip_in_networks(ip, networks):
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for network in networks:
        try:
            if address in ipaddress.ip_network(network, strict=False):
                return True
        except ValueError:
            if ip == network:
                return True
    return False


def get_client_ip(request):
    remote_addr = (request.META.get("REMOTE_ADDR") or "").strip()
    trusted_proxies = tuple(getattr(settings, "TRUSTED_PROXY_IPS", ()) or ())

    # Only trust forwarded headers when the direct peer is a known reverse proxy.
    if remote_addr and not _ip_in_networks(remote_addr, trusted_proxies):
        return remote_addr

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first

    real_ip = request.META.get("HTTP_X_REAL_IP", "").strip()
    if real_ip:
        return real_ip

    return remote_addr
