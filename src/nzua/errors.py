"""Винятки бібліотеки. Усі успадковують NZError."""

__all__ = (
    "NZError", "APIError", "IncorrectUsername", "IncorrectNickname",
    "IncorrectPassword", "HometaskNotFound", "Unauthorized", "SessionExpired",
    "ServiceUnavailable", "ConnectionTimedOut", "NetworkError",
    "RateLimited", "InternalServerError", "UnknownError",
)


class NZError(Exception):
    """Базовий виняток."""


class APIError(NZError):
    """Сервер повернув непорожнє `error_message`."""

    def __init__(self, message: str = "", response: dict | None = None) -> None:
        super().__init__(message or "Unknown API error")
        self.message = message
        self.response = response or {}


class IncorrectUsername(APIError):
    pass


IncorrectNickname = IncorrectUsername  # сумісність зі старою бібліотекою


class IncorrectPassword(APIError):
    pass


class HometaskNotFound(APIError):
    pass


class Unauthorized(NZError):
    def __init__(self) -> None:
        super().__init__("Невалідний токен. Викличте login().")


class SessionExpired(Unauthorized):
    """Токен не вдалося оновити: потрібно увійти знову."""

    def __init__(self) -> None:
        NZError.__init__(self, "Сесія завершилась. Увійдіть знову.")


class NetworkError(NZError):
    """Немає зв'язку з сервером."""


class ConnectionTimedOut(NetworkError):
    pass


class ServiceUnavailable(NetworkError):
    def __init__(self) -> None:
        super().__init__("Сервер тимчасово недоступний.")


class RateLimited(NZError):
    pass


class InternalServerError(NZError):
    pass


class UnknownError(NZError):
    pass
