from django.http.request import RawPostDataException
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from api.models import BlockedIP, SecurityEvent
from api.error_reporting import _request_body, sanitize_value
from api.views.security_actions import make_manual_block_token


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

    def test_request_body_ignores_consumed_raw_stream(self):
        class ConsumedStreamRequest:
            content_type = "application/json"
            FILES = None
            META = {}

            class _EmptyPost:
                @staticmethod
                def lists():
                    return []

            POST = _EmptyPost()

            @property
            def body(self):
                raise RawPostDataException(
                    "You cannot access body after reading from request's data stream"
                )

        self.assertIsNone(_request_body(ConsumedStreamRequest()))


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
        reply_markup = mock_post.call_args.kwargs["json"]["reply_markup"]
        self.assertIn("inline_keyboard", reply_markup)
        self.assertIn("Bloquear IP", reply_markup["inline_keyboard"][0][0]["text"])


@override_settings(
    TELEGRAM_SECURITY_ACTION_MAX_AGE_SECONDS=86400,
    TELEGRAM_MANUAL_BLOCK_MINUTES=60,
)
class TelegramSecurityActionTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_manual_block_token_blocks_ip(self):
        token = make_manual_block_token("203.0.113.44", path="/api/.env", method="GET")

        response = self.client.get("/api/security/manual-block-ip/", {"token": token})

        self.assertEqual(response.status_code, 200)
        block = BlockedIP.objects.get(ip_address="203.0.113.44")
        self.assertTrue(block.is_active)
        self.assertEqual(block.reason, "manual_telegram_block")
        self.assertTrue(SecurityEvent.objects.filter(ip_address="203.0.113.44", event_type="manual_telegram_block").exists())

    def test_manual_block_rejects_invalid_token(self):
        response = self.client.get("/api/security/manual-block-ip/", {"token": "bad-token"})

        self.assertEqual(response.status_code, 400)
