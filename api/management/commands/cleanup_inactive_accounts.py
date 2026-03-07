from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api.models import AccountActivationToken, Inmobiliaria, Usuario


class Command(BaseCommand):
    help = "Elimina cuentas inactivas pendientes de activacion con antiguedad mayor al umbral."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=int(getattr(settings, "ACCOUNT_PENDING_DELETE_DAYS", 7)),
            help="Dias de antiguedad para eliminar cuentas inactivas (default desde settings).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra lo que eliminaria sin ejecutar borrado.",
        )

    def handle(self, *args, **options):
        days = max(1, int(options["days"]))
        dry_run = bool(options["dry_run"])
        cutoff = timezone.now() - timedelta(days=days)

        pending_user_ids = list(
            AccountActivationToken.objects.filter(
                used_at__isnull=True,
                created_at__lte=cutoff,
                idusuario__is_active=False,
                idusuario__estado=0,
            )
            .values_list("idusuario_id", flat=True)
            .distinct()
        )

        if not pending_user_ids:
            self.stdout.write(self.style.SUCCESS("No hay cuentas pendientes para eliminar."))
            return

        user_count = Usuario.objects.filter(idusuario__in=pending_user_ids).count()
        inmo_count = Inmobiliaria.objects.filter(idusuario_id__in=pending_user_ids).count()
        token_count = AccountActivationToken.objects.filter(idusuario_id__in=pending_user_ids).count()

        self.stdout.write(
            f"Cuentas a eliminar: usuarios={user_count}, inmobiliarias={inmo_count}, tokens={token_count}, cutoff={cutoff.isoformat()}"
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run habilitado. No se realizaron cambios."))
            return

        with transaction.atomic():
            Inmobiliaria.objects.filter(idusuario_id__in=pending_user_ids).delete()
            AccountActivationToken.objects.filter(idusuario_id__in=pending_user_ids).delete()
            Usuario.objects.filter(idusuario__in=pending_user_ids).delete()

        self.stdout.write(self.style.SUCCESS("Limpieza completada correctamente."))
