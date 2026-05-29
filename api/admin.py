from django.contrib import admin

from .models import BlockedIP, SecurityEvent
from .security.services import clear_block_cache


@admin.register(BlockedIP)
class BlockedIPAdmin(admin.ModelAdmin):
    list_display = (
        "ip_address",
        "reason",
        "risk_score",
        "is_active",
        "is_permanent",
        "expires_at",
        "last_seen_at",
    )
    list_filter = ("is_active", "is_permanent", "reason", "created_at")
    search_fields = ("ip_address", "reason", "user_agent", "path")
    readonly_fields = ("created_at", "updated_at", "last_seen_at")
    ordering = ("-last_seen_at",)
    list_per_page = 50
    actions = ("deactivate_blocks",)

    @admin.action(description="Desactivar IPs bloqueadas seleccionadas")
    def deactivate_blocks(self, request, queryset):
        ips = list(queryset.values_list("ip_address", flat=True))
        updated = queryset.update(is_active=False)
        for ip in ips:
            clear_block_cache(ip)
        self.message_user(request, f"IPs desbloqueadas: {updated}")


@admin.register(SecurityEvent)
class SecurityEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "ip_address", "event_type", "action", "risk_score", "method", "path")
    list_filter = ("event_type", "action", "created_at")
    search_fields = ("ip_address", "path", "user_agent", "reason")
    date_hierarchy = "created_at"
    list_per_page = 50
    readonly_fields = (
        "ip_address",
        "method",
        "path",
        "user_agent",
        "event_type",
        "risk_score",
        "action",
        "reason",
        "metadata",
        "created_at",
    )
    ordering = ("-created_at",)
