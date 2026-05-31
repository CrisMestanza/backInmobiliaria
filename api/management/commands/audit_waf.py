import json
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import connection
from django.test import Client, override_settings

from api.models import BlockedIP, SecurityEvent
from api.security.conf import get_security_config
from api.security.detectors import is_sensitive_path
from api.security.services import clear_block_cache


DEFAULT_PROBES = [
    "/api/env",
    "/api/actuator/env",
    "/api/actuator/configprops",
    "/api/actuator/heapdump",
    "/api/heapdump",
    "/api/aws.json",
    "/api/credentials.json",
    "/api/phpinfo.php",
    "/api/docker-compose.yml",
    "/api/docker-compose.prod.yml",
    "/api/config.json",
    "/api/config.yml",
    "/api/appsettings.json",
    "/api/application.yml",
    "/api/application.properties",
    "/api/database.php",
    "/api/settings.json",
    "/api/settings.yml",
    "/api/secrets.json",
    "/api/keys.json",
    "/api/sonicos/is-sslvpn-enabled",
    "/api/v1/application.yml",
    "/api/v2/application.yml",
    "/api/v1/config.json",
    "/api/v2/config.json",
]


class Command(BaseCommand):
    help = "Audita el WAF usando el stack Django y la base configurada en este entorno."

    def add_arguments(self, parser):
        parser.add_argument("--ip", default="198.51.100.250")
        parser.add_argument("--host", default=(settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "testserver"))
        parser.add_argument("--max-probes", type=int, default=4)
        parser.add_argument("--no-write", action="store_true")

    def handle(self, *args, **options):
        ip = options["ip"]
        host = options["host"]
        probes = DEFAULT_PROBES[: max(1, options["max_probes"])]
        config = get_security_config()

        self.stdout.write("=== WAF AUDIT START ===")
        self.stdout.write(f"settings_module={settings.SETTINGS_MODULE}")
        self.stdout.write(f"base_dir={settings.BASE_DIR}")
        self.stdout.write(f"middleware_present={'api.security.middleware.InternalWAFMiddleware' in settings.MIDDLEWARE}")
        self.stdout.write(f"middleware_order={list(settings.MIDDLEWARE)}")
        self.stdout.write(f"waf_enabled={config.enabled}")
        self.stdout.write(f"ban_score={config.ban_score}")
        self.stdout.write(f"sensitive_hits_to_ban={config.sensitive_hits_to_ban}")
        self.stdout.write(f"api_prefixes={config.api_prefixes}")
        self.stdout.write(f"whitelist_ips={config.whitelist_ips}")
        self.stdout.write(f"db_vendor={connection.vendor}")
        self.stdout.write(f"db_name={connection.settings_dict.get('NAME')}")
        self.stdout.write(f"security_event_table={SecurityEvent._meta.db_table}")
        self.stdout.write(f"blocked_ip_table={BlockedIP._meta.db_table}")

        for probe in probes:
            self.stdout.write(f"detects {probe} => {is_sensitive_path(probe, config)}")

        if options["no_write"]:
            self.stdout.write("no_write=true; no se enviaron requests ni se escribio DB.")
            self.stdout.write("=== WAF AUDIT END ===")
            return

        clear_block_cache(ip)
        cache.delete(f"security:score:{ip}")
        BlockedIP.objects.filter(ip_address=ip).delete()
        SecurityEvent.objects.filter(ip_address=ip).delete()

        before_events = SecurityEvent.objects.filter(ip_address=ip).count()
        before_blocks = BlockedIP.objects.filter(ip_address=ip).count()
        self.stdout.write(f"before events={before_events} blocks={before_blocks}")

        allowed_hosts = list(dict.fromkeys([host, "testserver", *settings.ALLOWED_HOSTS]))
        with override_settings(ALLOWED_HOSTS=allowed_hosts):
            client = Client(
                REMOTE_ADDR=ip,
                HTTP_X_FORWARDED_FOR=ip,
                HTTP_USER_AGENT="GeoHabita-WAF-Audit/1.0",
                HTTP_HOST=host,
            )
            for path in probes:
                response = client.get(path, secure=True)
                self.stdout.write(
                    f"probe path={path} status={response.status_code} "
                    f"x_security_block={response.headers.get('X-Security-Block')}"
                )

            view_reached_marker = Path(settings.BASE_DIR) / ".waf_audit_view_marker"
            if view_reached_marker.exists():
                view_reached_marker.unlink()
            response = client.get("/api/listProyectos/", secure=True)
            self.stdout.write(
                f"post_ban_request path=/api/listProyectos/ status={response.status_code} "
                f"x_security_block={response.headers.get('X-Security-Block')}"
            )

        layer2_ip = "198.51.100.251" if ip != "198.51.100.251" else "198.51.100.252"
        SecurityEvent.objects.filter(ip_address=layer2_ip).delete()
        BlockedIP.objects.filter(ip_address=layer2_ip).delete()
        cache.delete(f"security:score:{layer2_ip}")
        with override_settings(ALLOWED_HOSTS=allowed_hosts):
            client = Client(
                REMOTE_ADDR=layer2_ip,
                HTTP_X_FORWARDED_FOR=layer2_ip,
                HTTP_USER_AGENT="GeoHabita-WAF-Audit/1.0",
                HTTP_HOST=host,
            )
            statuses = [
                client.get("/api/mapa/lote_detalle/999999999/", secure=True).status_code
                for _ in range(config.missing_hits_to_score)
            ]
            self.stdout.write(f"layer2_404_statuses={statuses}")

        events = list(
            SecurityEvent.objects.filter(ip_address=ip)
            .order_by("created_at")
            .values("event_type", "action", "risk_score", "reason", "path", "metadata")
        )
        blocks = list(
            BlockedIP.objects.filter(ip_address=ip)
            .values("ip_address", "reason", "risk_score", "is_active", "is_permanent", "expires_at", "path")
        )
        layer2_events = list(
            SecurityEvent.objects.filter(ip_address=layer2_ip)
            .order_by("created_at")
            .values("event_type", "action", "risk_score", "reason", "path", "metadata")
        )
        self.stdout.write(f"after events={len(events)} blocks={len(blocks)}")
        self.stdout.write("events_json=" + json.dumps(events, default=str, ensure_ascii=False))
        self.stdout.write("blocks_json=" + json.dumps(blocks, default=str, ensure_ascii=False))
        self.stdout.write("layer2_events_json=" + json.dumps(layer2_events, default=str, ensure_ascii=False))
        self.stdout.write("=== WAF AUDIT END ===")
