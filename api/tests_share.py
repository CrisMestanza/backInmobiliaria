from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from api.views.share import share_proyecto


class ShareProyectoViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.project = SimpleNamespace(
            idproyecto=167,
            nombreproyecto="Residencial Union Comercio",
            descripcion="Proyecto de prueba para compartir.",
            precio=25000,
            moneda="S/",
            idinmobiliaria=SimpleNamespace(idinmobiliaria=79),
        )

    @patch("api.views.share._get_project_or_404")
    def test_share_page_uses_share_url_as_canonical_and_og_url(self, mock_get_project):
        mock_get_project.return_value = self.project
        request = self.factory.get("/share/proyecto/167/", HTTP_HOST="api.geohabita.com")

        response = share_proyecto(request, 167)
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('<link rel="canonical" href="http://api.geohabita.com/share/proyecto/167/" />', content)
        self.assertIn('<meta property="og:url" content="http://api.geohabita.com/share/proyecto/167/" />', content)
        self.assertIn('<meta property="og:image:secure_url" content="http://api.geohabita.com/api/og-image/proyecto/167/" />', content)
        self.assertNotIn("http-equiv=\"refresh\"", content)
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow, noarchive")

    @patch("api.views.share._get_project_or_404")
    def test_share_page_disables_auto_redirect_for_whatsapp_bot(self, mock_get_project):
        mock_get_project.return_value = self.project
        request = self.factory.get(
            "/share/proyecto/167/",
            HTTP_HOST="api.geohabita.com",
            HTTP_USER_AGENT="WhatsApp/2.24",
        )

        response = share_proyecto(request, 167)
        content = response.content.decode("utf-8")

        self.assertIn('var shouldRedirect = "false" === "true";', content)
