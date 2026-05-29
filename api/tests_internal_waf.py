from django.core.cache import cache
from django.http import JsonResponse
from django.test import RequestFactory
from django.test import Client, TestCase, override_settings

from api.models import BlockedIP, SecurityEvent
from api.security.services import observe_security_response


WAF_TEST_SETTINGS = {
    "ENABLED": True,
    "WHITELIST_IPS": (),
    "API_PREFIXES": ("/api/",),
    "RATE_LIMIT_PER_MINUTE": 100,
    "BURST_LIMIT_PER_10_SECONDS": 100,
    "CONCURRENT_LIMIT": 20,
    "TEMP_BAN_MINUTES": 60,
    "BAN_SCORE": 100,
    "PERMANENT_SCORE": 200,
    "SENSITIVE_HITS_TO_BAN": 3,
    "MISSING_HITS_TO_SCORE": 8,
    "BODY_INSPECTION_BYTES": 16384,
    "LOG_SAMPLE_SECONDS": 60,
    "BLOCK_NEGATIVE_CACHE_SECONDS": 120,
    "CLEANUP_INTERVAL_SECONDS": 0,
    "EVENT_RETENTION_DAYS": 30,
    "MAX_SECURITY_EVENTS": 50000,
    "CLEANUP_BATCH_SIZE": 1000,
    "DEBUG_LOGS": False,
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
        self.assertEqual(self.client.get("/api/.env").status_code, 403)
        self.assertEqual(self.client.get("/api/openapi.json").status_code, 403)
        third = self.client.get("/api/schema")

        self.assertEqual(third.status_code, 403)
        block = BlockedIP.objects.get(ip_address="203.0.113.10")
        self.assertTrue(block.is_active)
        self.assertFalse(block.is_permanent)
        self.assertEqual(block.reason, "repeated_sensitive_path_probe")

    def test_pycache_probe_is_treated_as_sensitive(self):
        response = self.client.get("/api/__pycache__/settings.cpython-311.pyc")

        self.assertEqual(response.status_code, 403)
        self.assertTrue(SecurityEvent.objects.filter(event_type="sensitive_path").exists())

    def test_partial_sensitive_path_variants_are_blocked(self):
        probes = [
            "/api/.env.staging",
            "/api/config.yml",
            "/api/settings.json",
            "/api/docker-compose.prod.yml",
            "/api/credentials.json",
            "/api/actuator/heapdump",
        ]

        for index, path in enumerate(probes, start=1):
            client = Client(REMOTE_ADDR=f"203.0.113.{index + 20}", HTTP_USER_AGENT="Mozilla/5.0")
            response = client.get(path)
            self.assertEqual(response.status_code, 403)

        self.assertEqual(SecurityEvent.objects.filter(event_type="sensitive_path").count(), len(probes))

    def test_blocked_ip_short_circuits_next_request(self):
        BlockedIP.objects.create(
            ip_address="203.0.113.99",
            reason="risk_score_threshold",
            risk_score=100,
            is_active=True,
        )
        client = Client(REMOTE_ADDR="203.0.113.99", HTTP_USER_AGENT="Mozilla/5.0")

        response = client.get("/api/listProyectos/")

        self.assertEqual(response.status_code, 403)
        self.assertTrue(SecurityEvent.objects.filter(event_type="blocked_ip_request").exists())

    def test_response_observer_scores_sensitive_404_and_bans(self):
        factory = RequestFactory(REMOTE_ADDR="203.0.113.80", HTTP_USER_AGENT="Mozilla/5.0")

        for path in ("/api/.env", "/api/graphql", "/api/sonicos/is-sslvpn-enabled"):
            request = factory.get(path)
            response = JsonResponse({"detail": "not found"}, status=404)
            observe_security_response(request, response)

        self.assertTrue(
            SecurityEvent.objects.filter(
                ip_address="203.0.113.80",
                event_type="sensitive_response_path",
            ).exists()
        )
        block = BlockedIP.objects.get(ip_address="203.0.113.80")
        self.assertTrue(block.is_active)
        self.assertEqual(block.reason, "repeated_sensitive_path_probe")

    def test_response_observer_404_flood_uses_shared_score(self):
        factory = RequestFactory(REMOTE_ADDR="203.0.113.81", HTTP_USER_AGENT="Mozilla/5.0")

        for index in range(8):
            request = factory.get(f"/api/no-real-route-{index}/")
            response = JsonResponse({"detail": "not found"}, status=404)
            observe_security_response(request, response)

        self.assertTrue(
            SecurityEvent.objects.filter(
                ip_address="203.0.113.81",
                event_type="not_found_flood",
            ).exists()
        )

    def test_repeated_identical_events_are_sampled(self):
        factory = RequestFactory(REMOTE_ADDR="203.0.113.82", HTTP_USER_AGENT="Mozilla/5.0")

        for _ in range(12):
            request = factory.get("/api/no-real-route/")
            response = JsonResponse({"detail": "not found"}, status=404)
            observe_security_response(request, response)

        self.assertLessEqual(
            SecurityEvent.objects.filter(
                ip_address="203.0.113.82",
                event_type="not_found_flood",
                path="/api/no-real-route/",
            ).count(),
            1,
        )
