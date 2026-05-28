from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from api.models import BlockedIP, SecurityEvent


WAF_TEST_SETTINGS = {
    "ENABLED": True,
    "WHITELIST_IPS": (),
    "API_PREFIXES": ("/api/",),
    "RATE_LIMIT_PER_MINUTE": 100,
    "BURST_LIMIT_PER_10_SECONDS": 100,
    "CONCURRENT_LIMIT": 20,
    "TEMP_BAN_MINUTES": 60,
    "BAN_SCORE": 70,
    "PERMANENT_SCORE": 140,
    "SENSITIVE_HITS_TO_BAN": 3,
    "MISSING_HITS_TO_SCORE": 8,
    "BODY_INSPECTION_BYTES": 16384,
    "LOG_SAMPLE_SECONDS": 0,
}


@override_settings(SECURITY_WAF=WAF_TEST_SETTINGS)
class InternalWAFMiddlewareTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(REMOTE_ADDR="203.0.113.10", HTTP_USER_AGENT="Mozilla/5.0")

    def test_sql_injection_payload_is_banned_immediately(self):
        response = self.client.get("/api/listProyectos/", {"q": "' OR 1=1--"})

        self.assertEqual(response.status_code, 403)
        self.assertTrue(BlockedIP.objects.filter(ip_address="203.0.113.10", is_active=True).exists())
        self.assertTrue(SecurityEvent.objects.filter(event_type="ip_banned", reason="sql_injection_payload").exists())

    def test_sql_injection_json_login_body_is_banned_immediately(self):
        response = self.client.post(
            "/api/login/",
            data='{"correo": "\' UNION SELECT 1--", "password": "x"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(BlockedIP.objects.filter(ip_address="203.0.113.10", is_active=True).exists())

    def test_repeated_sensitive_paths_create_temporary_ban(self):
        self.assertEqual(self.client.get("/api/.env").status_code, 404)
        self.assertEqual(self.client.get("/api/openapi.json").status_code, 404)
        third = self.client.get("/api/schema")

        self.assertEqual(third.status_code, 403)
        block = BlockedIP.objects.get(ip_address="203.0.113.10")
        self.assertTrue(block.is_active)
        self.assertFalse(block.is_permanent)
        self.assertEqual(block.reason, "repeated_sensitive_path_probe")

    def test_pycache_probe_is_treated_as_sensitive(self):
        response = self.client.get("/api/__pycache__/settings.cpython-311.pyc")

        self.assertEqual(response.status_code, 404)
        self.assertTrue(SecurityEvent.objects.filter(event_type="sensitive_path").exists())
