from django.core.management.base import BaseCommand

from api.models import BlockedIP, SecurityEvent
from api.security.conf import get_security_config
from api.security.services import cleanup_security_records, clear_block_cache


class Command(BaseCommand):
    help = "Limpia bloqueos expirados y eventos antiguos/excesivos del WAF interno."

    def add_arguments(self, parser):
        parser.add_argument("--event-retention-days", type=int)
        parser.add_argument("--max-security-events", type=int)
        parser.add_argument("--cleanup-batch-size", type=int)
        parser.add_argument("--list-blocked", action="store_true")
        parser.add_argument("--unblock-ip")
        parser.add_argument("--recent-events", type=int)

    def handle(self, *args, **options):
        if options.get("list_blocked"):
            blocks = BlockedIP.objects.filter(is_active=True).order_by("-last_seen_at")[:50]
            for block in blocks:
                self.stdout.write(
                    f"{block.ip_address} score={block.risk_score} reason={block.reason} "
                    f"expires_at={block.expires_at or 'permanent'} last_seen={block.last_seen_at}"
                )
            if not blocks:
                self.stdout.write("No hay IPs bloqueadas activas.")
            return

        if options.get("unblock_ip"):
            ip = options["unblock_ip"]
            updated = BlockedIP.objects.filter(ip_address=ip, is_active=True).update(is_active=False)
            clear_block_cache(ip)
            self.stdout.write(self.style.SUCCESS(f"IP desbloqueada={ip} registros_actualizados={updated}"))
            return

        if options.get("recent_events"):
            events = SecurityEvent.objects.order_by("-created_at")[: options["recent_events"]]
            for event in events:
                self.stdout.write(
                    f"{event.created_at} {event.ip_address} {event.event_type} "
                    f"action={event.action} score={event.risk_score} path={event.path}"
                )
            if not events:
                self.stdout.write("No hay eventos de seguridad.")
            return

        config = get_security_config()
        if (
            options.get("event_retention_days") is not None
            or options.get("max_security_events") is not None
            or options.get("cleanup_batch_size") is not None
        ):
            config = config.__class__(
                **{
                    **config.__dict__,
                    "event_retention_days": options.get("event_retention_days") or config.event_retention_days,
                    "max_security_events": options.get("max_security_events") or config.max_security_events,
                    "cleanup_batch_size": options.get("cleanup_batch_size") or config.cleanup_batch_size,
                }
            )
        result = cleanup_security_records(config)
        self.stdout.write(
            self.style.SUCCESS(
                "Limpieza WAF completada: "
                f"bans_expirados={result['expired_blocks']}, "
                f"eventos_antiguos={result['old_events_deleted']}, "
                f"eventos_por_limite={result['capped_events_deleted']}"
            )
        )
