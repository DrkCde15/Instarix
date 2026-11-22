"""Perfil de dispositivo do Instagram, gerado uma vez por conta.

Reutilizar o mesmo perfil (uuids, device, user agent, locale) em todas as
tentativas é o que evita que o login pareça um aparelho novo — principal
gatilho de checkpoint. Nunca incluir aqui cookies/autorização/sessão.
"""

from typing import Any, Protocol

# Chaves de sessão/autenticação que jamais entram no perfil persistido.
EXCLUDED_SETTINGS = frozenset(
    {
        "authorization_data",
        "cookies",
        "last_login",
        "ig_u_rur",
        "ig_www_claim",
        "fbns_auth",
        "usdid",
        "mid",  # identificador de máquina ligado à sessão
    }
)


class DeviceProfileProvider(Protocol):
    def generate(self) -> dict[str, Any]: ...


class InstagrapiDeviceProfileProvider:
    """Gera um perfil novo a partir de um Client vazio (sem rede)."""

    def generate(self) -> dict[str, Any]:
        from instagrapi import Client

        settings = Client().get_settings()
        profile = {k: v for k, v in settings.items() if k not in EXCLUDED_SETTINGS}
        if not profile.get("device_settings") or not profile.get("uuids"):
            raise RuntimeError("instagrapi não retornou um perfil de dispositivo utilizável")
        return profile


def get_device_provider() -> DeviceProfileProvider:
    return InstagrapiDeviceProfileProvider()
