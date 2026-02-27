from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework.exceptions import AuthenticationFailed
from .models import Usuario

class CustomJWTAuthentication(JWTAuthentication):
    """
    Autenticación JWT personalizada para usar el campo idusuario
    y permitir vistas públicas sin token.
    """
    def authenticate(self, request):
        """
        No intenta autenticar si la vista permite acceso público (AllowAny)
        o si no hay encabezado Authorization.
        """
        auth_header = self.get_header(request)
        if auth_header is None:
            return None

        try:
            raw_token = self.get_raw_token(auth_header)
            if raw_token is None:
                raise AuthenticationFailed("Formato de token inválido")
            validated_token = self.get_validated_token(raw_token)
            return self.get_user(validated_token), validated_token
        except (InvalidToken, AuthenticationFailed):
            raise AuthenticationFailed("Token inválido o expirado")

    def get_user(self, validated_token):
        try:
            user_id = validated_token.get("user_id")
            return Usuario.objects.get(idusuario=user_id)
        except Usuario.DoesNotExist:
            raise InvalidToken("Usuario no encontrado")
