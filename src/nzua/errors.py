"""Винятки бібліотеки. Усі успадковують NZError."""

__all__ = (
    "NZError", "APIError", "IncorrectUsername", "IncorrectNickname",
    "IncorrectPassword", "HometaskNotFound", "Unauthorized", "SessionExpired",
    "ServiceUnavailable", "ConnectionTimedOut", "NetworkError",
    "RateLimited", "InternalServerError", "UnknownError", "BlockedError",
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


class BlockedError(NetworkError):
    """Захист сервера (Cloudflare «Just a moment...») відхилив запит."""

    def __init__(self, status: int = 403) -> None:
        super().__init__(
            f"Сервер nz.ua заблокував запит (захист Cloudflare, HTTP {status}). "
            "Виконайте `python -m nzua diagnose --save` — воно підбере спосіб, що проходить. "
            "Також спробуйте вимкнути VPN або змінити мережу.")
        self.status = status


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
