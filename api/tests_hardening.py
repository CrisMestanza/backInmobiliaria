from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from api.request_utils import get_client_ip
from api.views.imagen360Casa import guardar_tour_360_completo


class ClientIPHardeningTests(SimpleTestCase):
    @override_settings(TRUSTED_PROXY_IPS=())
    def test_untrusted_forwarded_for_is_ignored(self):
        request = SimpleNamespace(
            META={
                "REMOTE_ADDR": "198.51.100.10",
                "HTTP_X_FORWARDED_FOR": "1.2.3.4",
            }
        )

        self.assertEqual(get_client_ip(request), "198.51.100.10")

    @override_settings(TRUSTED_PROXY_IPS=("198.51.100.10",))
    def test_trusted_proxy_forwarded_for_is_used(self):
        request = SimpleNamespace(
            META={
                "REMOTE_ADDR": "198.51.100.10",
                "HTTP_X_FORWARDED_FOR": "203.0.113.55, 198.51.100.10",
            }
        )

        self.assertEqual(get_client_ip(request), "203.0.113.55")


class Tour360PermissionTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_tour_360_write_requires_authentication(self):
        request = self.factory.post(
            "/api/guardar_tour_360_completo/",
            {"idproyecto": "1"},
            format="multipart",
        )

        response = guardar_tour_360_completo(request)

        self.assertIn(response.status_code, (401, 403))

    @patch("api.views.imagen360Casa.is_project_owned_by_user", return_value=False)
    def test_tour_360_write_rejects_non_owner(self, _owned):
        request = self.factory.post(
            "/api/guardar_tour_360_completo/",
            {"idproyecto": "1"},
            format="multipart",
        )
        force_authenticate(request, user=SimpleNamespace(idusuario=7, is_authenticated=True))

        response = guardar_tour_360_completo(request)

        self.assertEqual(response.status_code, 403)
