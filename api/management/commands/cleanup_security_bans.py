from django.core.management.base import BaseCommand

from api.security.services import cleanup_expired_blocks


class Command(BaseCommand):
    help = "Desactiva bloqueos temporales expirados del mini WAF interno."

    def handle(self, *args, **options):
        updated = cleanup_expired_blocks()
        self.stdout.write(self.style.SUCCESS(f"Bloqueos expirados desactivados: {updated}"))
