from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from rest_framework_simplejwt.exceptions import InvalidToken

from .authentication import CustomJWTAuthentication
from .security_uploads import build_secure_image_name, validate_uploaded_image
from .throttling import LoginRateThrottle
from .views.inmobiliaria import updateInmobiliaria
from .views.usuario import updateUsuario, listUsuarios
from .serializers import InmobiliariaRegistroSerializer


def _png_file(name="ok.png", size=(10, 10)):
    buf = BytesIO()
    image = Image.new("RGB", size=size, color=(255, 0, 0))
    image.save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _auth_user(user_id=1, is_superuser=False):
    return SimpleNamespace(idusuario=user_id, pk=user_id, is_authenticated=True, is_superuser=is_superuser)


class AuthSecurityTests(SimpleTestCase):
    def test_invalid_token_raises_exception(self):
        request = APIRequestFactory().get("/api/check_auth/")
        auth = CustomJWTAuthentication()

        with patch.object(auth, "get_header", return_value=b"Bearer bad"), \
             patch.object(auth, "get_raw_token", return_value=b"bad"), \
             patch.object(auth, "get_validated_token", side_effect=InvalidToken("bad")):
            with self.assertRaises(AuthenticationFailed):
                auth.authenticate(request)


class PermissionSecurityTests(SimpleTestCase):
    def test_update_usuario_requires_owner(self):
        request = APIRequestFactory().put("/api/updateUsuario/2/", {"nombre": "X"}, format="json")
        force_authenticate(request, user=_auth_user(1))
        response = updateUsuario(request, idusuario=2)
        self.assertEqual(response.status_code, 403)

    @patch("api.views.usuario.Usuario.objects.filter")
    def test_update_usuario_blocks_privilege_fields(self, mock_filter):
        mock_filter.return_value.first.return_value = SimpleNamespace(idusuario=1)
        request = APIRequestFactory().put(
            "/api/updateUsuario/1/",
            {"is_superuser": True},
            format="json",
        )
        force_authenticate(request, user=_auth_user(1))
        response = updateUsuario(request, idusuario=1)
        self.assertEqual(response.status_code, 403)

    def test_list_usuarios_requires_superuser(self):
        request = APIRequestFactory().get("/api/listUsuarios/")
        force_authenticate(request, user=_auth_user(1))
        response = listUsuarios(request)
        self.assertEqual(response.status_code, 403)

    @patch("api.views.inmobiliaria.Inmobiliaria.objects.get")
    def test_update_inmobiliaria_requires_owner(self, mock_get):
        mock_get.return_value = SimpleNamespace(idusuario_id=77)
        request = APIRequestFactory().put("/api/updateInmobiliaria/1/", {"nombreinmobiliaria": "x"}, format="json")
        force_authenticate(request, user=_auth_user(1))
        response = updateInmobiliaria(request, idinmobiliaria=1)
        self.assertEqual(response.status_code, 403)


class UploadSecurityTests(SimpleTestCase):
    def test_rejects_extension_not_allowed(self):
        gif = SimpleUploadedFile("x.gif", b"GIF89a", content_type="image/gif")
        with self.assertRaises(ValidationError):
            validate_uploaded_image(gif)

    @override_settings(MAX_IMAGE_UPLOAD_MB=1)
    def test_rejects_oversized_image(self):
        big = SimpleUploadedFile("big.png", b"a" * (2 * 1024 * 1024), content_type="image/png")
        with self.assertRaises(ValidationError):
            validate_uploaded_image(big)

    def test_accepts_valid_png(self):
        file_obj = _png_file()
        validate_uploaded_image(file_obj)

    @override_settings(ANTIVIRUS_ENABLED=True, ANTIVIRUS_COMMAND="clamscan", ANTIVIRUS_STRICT=True)
    @patch("api.security_uploads.shutil.which", return_value="/usr/bin/clamscan")
    @patch("api.security_uploads.subprocess.run")
    def test_antivirus_rejects_infected_file(self, mock_run, _mock_which):
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="FOUND", stderr="")
        file_obj = _png_file()
        with self.assertRaises(ValidationError):
            validate_uploaded_image(file_obj)

    def test_secure_rename_structure(self):
        name = build_secure_image_name(10, 50, "lote", "foto.jpeg")
        self.assertTrue(name.startswith("inmo_10/proy_50/lote_"))
        self.assertTrue(name.endswith(".jpg"))


class ThrottleSecurityTests(SimpleTestCase):
    @override_settings(
        SECURE_SSL_REDIRECT=False,
        REST_FRAMEWORK={
            "DEFAULT_AUTHENTICATION_CLASSES": ("api.authentication.CustomJWTAuthentication",),
            "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
            "DEFAULT_THROTTLE_CLASSES": (
                "rest_framework.throttling.AnonRateThrottle",
                "rest_framework.throttling.UserRateThrottle",
                "rest_framework.throttling.ScopedRateThrottle",
            ),
            "DEFAULT_THROTTLE_RATES": {
                "anon": "100/hour",
                "user": "1000/hour",
                "login": "2/minute",
                "refresh": "20/minute",
                "clicks": "60/minute",
            },
        }
    )
    @patch("api.views.usuario.LoginSerializer")
    def test_login_rate_limit(self, serializer_cls):
        serializer = serializer_cls.return_value
        serializer.is_valid.return_value = False
        serializer.errors = {"detail": "bad"}

        cache.clear()
        client = APIClient()
        LoginRateThrottle.rate = "2/minute"

        r1 = client.post("/api/login/", {"correo": "a@a.com", "password": "x"}, format="json")
        r2 = client.post("/api/login/", {"correo": "a@a.com", "password": "x"}, format="json")
        r3 = client.post("/api/login/", {"correo": "a@a.com", "password": "x"}, format="json")

        self.assertEqual(r1.status_code, 400)
        self.assertEqual(r2.status_code, 400)
        self.assertEqual(r3.status_code, 429)


class RegistrationSecurityTests(SimpleTestCase):
    @patch("api.serializers.transaction.atomic")
    @patch("api.serializers.Inmobiliaria.objects.create")
    @patch("api.serializers.Usuario.objects.create")
    def test_inmobiliaria_serializer_forces_non_superuser(
        self, mock_user_create, mock_inmo_create, mock_atomic
    ):
        mock_atomic.return_value.__enter__.return_value = None
        mock_atomic.return_value.__exit__.return_value = False
        mock_user = SimpleNamespace(idusuario=10)
        mock_user_create.return_value = mock_user
        mock_inmo_create.return_value = SimpleNamespace(idinmobiliaria=50)

        serializer = InmobiliariaRegistroSerializer(
            data={
                "nombreinmobiliaria": "X",
                "descripcion": "Y",
                "telefono": "999",
                "correo": "x@x.com",
                "usuario": {
                    "correo": "evil@x.com",
                    "password": "SuperSecure123!",
                    "nombre": "evil",
                    "is_superuser": True,
                    "is_staff": True,
                },
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()

        kwargs = mock_user_create.call_args.kwargs
        self.assertFalse(kwargs["is_superuser"])
        self.assertFalse(kwargs["is_staff"])
