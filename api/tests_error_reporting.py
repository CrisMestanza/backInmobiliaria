from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from api.error_reporting import sanitize_value


class ErrorReportingSanitizeTests(SimpleTestCase):
    def test_sanitize_masks_sensitive_fields(self):
        payload = {
            "password": "mi-clave-super-secreta",
            "token": "1234567890abcdef",
            "nested": {
                "authorization": "Bearer abcdefghijklmnop",
            },
        }

        sanitized = sanitize_value(payload)

        self.assertIn("[redacted]", sanitized["password"])
        self.assertIn("[redacted]", sanitized["token"])
        self.assertIn("[redacted]", sanitized["nested"]["authorization"])


@override_settings(
    TELEGRAM_ERROR_ALERTS_ENABLED=True,
    TELEGRAM_BOT_TOKEN="bot-token",
    TELEGRAM_CHAT_ID="chat-id",
)
class FrontendErrorReportViewTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("api.error_reporting.requests.post")
    def test_frontend_error_report_sends_telegram_message(self, mock_post):
        response = self.client.post(
            "/api/frontend-error-report/",
            {
                "message": "Fallo al guardar proyecto",
                "payload": {
                    "kind": "http",
                    "route": "/mapa/1",
                    "userAction": "Intento de registrar proyecto",
                    "request": {
                        "url": "https://api.geohabita.com/api/registerProyecto/",
                        "method": "POST",
                        "body": {"nombre": "Demo", "password": "secret-1234"},
                    },
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        self.assertTrue(mock_post.called)
        posted_message = mock_post.call_args.kwargs["json"]["text"]
        self.assertIn("GeoHabita", posted_message)
        self.assertIn("/mapa/1", posted_message)
        self.assertIn("[redacted]", posted_message)
        self.assertIn("Intento de registrar proyecto", posted_message)
        self.assertNotIn("body_error", posted_message)
