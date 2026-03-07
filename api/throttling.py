from rest_framework.throttling import SimpleRateThrottle


class BaseIPThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        if not ident:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }


class LoginRateThrottle(BaseIPThrottle):
    scope = "login"


class RefreshRateThrottle(BaseIPThrottle):
    scope = "refresh"


class ClickRateThrottle(BaseIPThrottle):
    scope = "clicks"


class RegisterRateThrottle(BaseIPThrottle):
    scope = "register"


class RecoveryRequestRateThrottle(BaseIPThrottle):
    scope = "recovery_request"


class RecoveryVerifyRateThrottle(BaseIPThrottle):
    scope = "recovery_verify"


class RecoveryResetRateThrottle(BaseIPThrottle):
    scope = "recovery_reset"


class ActivationResendRateThrottle(BaseIPThrottle):
    scope = "activation_resend"
