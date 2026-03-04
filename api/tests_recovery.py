from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from api.views.usuario import (
    recovery_request_code,
    recovery_verify_code,
    recovery_reset_password,
)


def _qs_with_first(value):
    qs = MagicMock()
    qs.first.return_value = value
    qs.only.return_value = qs
    qs.order_by.return_value = qs
    return qs


class RecoveryViewsTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    @patch("api.views.usuario.PasswordResetCode.objects.create")
    @patch("api.views.usuario.PasswordResetCode.objects.filter")
    @patch("api.views.usuario.Usuario.objects.filter")
    @patch("api.views.usuario._send_recovery_email")
    def test_request_code_creates_entry_and_sends_mail(
        self, mock_send, mock_user_filter, mock_reset_filter, mock_reset_create
    ):
        user = SimpleNamespace(idusuario=1, correo="user@example.com")
        mock_user_filter.return_value = _qs_with_first(user)
        mock_reset_filter.return_value = _qs_with_first(None)

        request = self.factory.post(
            "/api/recovery/request-code/",
            {"correo": "user@example.com"},
            format="json",
        )
        response = recovery_request_code(request)

        self.assertEqual(response.status_code, 200)
        mock_reset_create.assert_called_once()
        mock_send.assert_called_once()

    @patch("api.views.usuario.check_password", return_value=True)
    @patch("api.views.usuario.PasswordResetCode.objects.filter")
    @patch("api.views.usuario.Usuario.objects.filter")
    @patch("api.views.usuario.Inmobiliaria.objects.filter")
    def test_verify_code_returns_profile_and_token(
        self, mock_inmo_filter, mock_user_filter, mock_reset_filter, _mock_check_password
    ):
        user = SimpleNamespace(
            idusuario=2,
            correo="owner@example.com",
            nombre="Owner",
            estado=1,
            is_active=True,
        )
        reset_entry = SimpleNamespace(
            codigo_hash="hash",
            attempts=0,
            expires_at=timezone.now() + timedelta(minutes=5),
            save=MagicMock(),
        )
        inmo = SimpleNamespace(
            idinmobiliaria=7,
            nombreinmobiliaria="Inmo Test",
            telefono="999999999",
            correo="inmo@example.com",
            whatsapp="900000000",
        )

        mock_user_filter.return_value = _qs_with_first(user)
        mock_reset_filter.return_value = _qs_with_first(reset_entry)
        mock_inmo_filter.return_value = _qs_with_first(inmo)

        request = self.factory.post(
            "/api/recovery/verify-code/",
            {"correo": "owner@example.com", "codigo": "123456"},
            format="json",
        )
        response = recovery_verify_code(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("reset_token", response.data)
        self.assertEqual(response.data["usuario"]["correo"], "owner@example.com")
        self.assertEqual(response.data["inmobiliaria"]["idinmobiliaria"], 7)

    @patch("api.views.usuario.PasswordResetCode.objects.filter")
    @patch("api.views.usuario.Usuario.objects.filter")
    def test_reset_password_uses_set_password(self, mock_user_filter, mock_reset_filter):
        user = MagicMock()
        user.correo = "owner@example.com"
        user.estado = 1
        user.is_active = True
        reset_entry = MagicMock()
        reset_entry.expires_at = timezone.now() + timedelta(minutes=5)

        mock_user_filter.return_value = _qs_with_first(user)
        mock_reset_filter.return_value = _qs_with_first(reset_entry)

        request = self.factory.post(
            "/api/recovery/reset-password/",
            {
                "correo": "owner@example.com",
                "reset_token": "token123",
                "password": "NuevaClaveSegura123!",
            },
            format="json",
        )
        response = recovery_reset_password(request)

        self.assertEqual(response.status_code, 200)
        user.set_password.assert_called_once_with("NuevaClaveSegura123!")
        user.save.assert_called_once()
