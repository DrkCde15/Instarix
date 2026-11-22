"""Aplicação FastAPI do backend Instarix."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.crypto import get_cipher
from app.core.errors import AppError
from app.core.logging import RequestContextMiddleware, configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    get_cipher()  # falha cedo se SECRETS_KEYS estiver inválido

    app = FastAPI(title="Instarix API", version="0.1.0")

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
            headers=exc.headers or None,
        )

    app.include_router(health_router)
    app.include_router(api_router, prefix="/v1")
    return app


app = create_app()
