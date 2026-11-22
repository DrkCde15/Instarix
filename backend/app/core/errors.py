"""Erros de aplicação com código estável para o cliente."""


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


def not_found(code: str = "not_found", message: str = "Recurso não encontrado.") -> AppError:
    return AppError(404, code, message)


def forbidden(code: str = "forbidden", message: str = "Permissão negada.") -> AppError:
    return AppError(403, code, message)


def conflict(code: str, message: str) -> AppError:
    return AppError(409, code, message)


def unauthorized(code: str = "unauthorized", message: str = "Autenticação inválida.") -> AppError:
    return AppError(401, code, message)
