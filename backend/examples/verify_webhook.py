"""Exemplo de receptor de webhooks do Instarix, usando apenas a stdlib.

O segredo vem de ``INSTARIX_WEBHOOK_SECRET`` (nunca de arquivo e nunca impresso).

Uso:
    export INSTARIX_WEBHOOK_SECRET='<segredo-exibido-na-criacao>'
    python examples/verify_webhook.py --selftest      # testa a lógica sem rede
    python examples/verify_webhook.py --port 8080     # receptor local

O Instarix bloqueia URLs localhost/privadas. Para testar a entrega real, use
um túnel com hostname público apontando para esta porta.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

MAX_AGE_SECONDS = 300  # tolerância para replay; ajuste ao seu relógio/clock skew


def verify_signature(
    secret: str,
    timestamp: str,
    body: bytes,
    signature: str,
    *,
    now: float | None = None,
    max_age_seconds: int = MAX_AGE_SECONDS,
) -> None:
    """Valida assinatura e idade do evento; levanta ValueError se inválido."""
    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise ValueError("timestamp inválido") from exc

    current = time.time() if now is None else now
    if abs(current - sent_at) > max_age_seconds:
        raise ValueError("timestamp fora da janela permitida")

    if not signature.startswith("sha256="):
        raise ValueError("formato de assinatura inválido")

    expected = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature.removeprefix("sha256=")):
        raise ValueError("assinatura inválida")


def _required(headers: Any, name: str) -> str:
    value = headers.get(name)
    if not value:
        raise ValueError(f"header ausente: {name}")
    return value


class WebhookHandler(BaseHTTPRequestHandler):
    server_version = "InstarixWebhookExample/1.0"

    def do_GET(self) -> None:  # noqa: N802 - API do http.server
        self._respond(
            200,
            {
                "status": "ok",
                "message": "Endpoint de exemplo: envie um POST com os headers X-Instarix-*.",
            },
        )

    def do_POST(self) -> None:  # noqa: N802 - API do http.server
        secret = os.environ.get("INSTARIX_WEBHOOK_SECRET", "")
        if not secret:
            self._respond(500, {"error": "INSTARIX_WEBHOOK_SECRET não configurado"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._respond(400, {"error": "Content-Length inválido"})
            return
        if length <= 0 or length > 1_000_000:
            self._respond(413, {"error": "corpo inválido"})
            return
        body = self.rfile.read(length)

        event = self.headers.get("X-Instarix-Event", "")
        delivery_id = self.headers.get("X-Instarix-Delivery", "")
        try:
            timestamp = _required(self.headers, "X-Instarix-Timestamp")
            signature = _required(self.headers, "X-Instarix-Signature")
            verify_signature(secret, timestamp, body, signature)
        except ValueError as exc:
            self._respond(401, {"error": str(exc)})
            return

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._respond(400, {"error": "JSON inválido"})
            return

        print(f"[{event}] entrega={delivery_id} payload={payload}", flush=True)
        self._respond(204, None)  # 2xx confirma a entrega

    def _respond(self, status: int, body: dict[str, str] | None) -> None:
        data = b"" if body is None else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def log_message(self, fmt: str, *args: object) -> None:
        return  # saída só com eventos relevantes


def selftest(secret: str) -> None:
    body = json.dumps(
        {"job_id": "exemplo", "type": "media.list", "status": "succeeded"},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    timestamp = str(int(time.time()))
    signature = "sha256=" + hmac.new(
        secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()

    verify_signature(secret, timestamp, body, signature)

    for label, bad_timestamp, bad_signature in (
        ("assinatura errada", timestamp, "sha256=" + "0" * 64),
        ("evento antigo", str(int(time.time()) - 3600), signature),
    ):
        try:
            verify_signature(secret, bad_timestamp, body, bad_signature)
        except ValueError:
            continue
        raise SystemExit(f"selftest falhou: {label} foi aceito")

    print("selftest OK: assinatura válida aceita; inválida e antiga rejeitadas.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)

    secret = os.environ.get("INSTARIX_WEBHOOK_SECRET", "")
    if not secret:
        parser.error("defina INSTARIX_WEBHOOK_SECRET no ambiente")

    if args.selftest:
        selftest(secret)
        return 0

    server = HTTPServer((args.host, args.port), WebhookHandler)
    print(f"ouvindo em http://{args.host}:{args.port} (Ctrl+C para sair)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
