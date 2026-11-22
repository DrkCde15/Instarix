import pytest
from instagrapi import Client
from instagrapi.exceptions import (
    BadPassword,
    ChallengeRequired,
    ClientConnectionError,
    ClientError,
    LoginRequired,
    TwoFactorRequired,
)

from app.services.ig_gateway import InstagrapiGateway


@pytest.fixture
def device_settings() -> dict:
    return Client().get_settings()


def login_via_gateway(device_settings: dict):
    return InstagrapiGateway().login(
        username="conta",
        password="senha",
        device_settings=device_settings,
        proxy=None,
    )


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TwoFactorRequired(), "2fa_required"),
        (ChallengeRequired(), "challenge_required"),
        (BadPassword(), "bad_password"),
        (ClientConnectionError(), "unavailable"),
        (ClientError("boom"), "unavailable"),
    ],
)
def test_login_maps_instagrapi_errors(
    monkeypatch, device_settings, error, expected
):
    def fail(self, **kwargs):
        raise error

    monkeypatch.setattr(Client, "login", fail)
    outcome = login_via_gateway(device_settings)
    assert outcome.status == expected
    if expected != "ok":
        assert outcome.session is None


def test_login_returns_full_session_on_success(monkeypatch, device_settings):
    session = {"cookies": {"sessionid": "abc"}, "authorization_data": {"ds_user_id": "1"}}
    monkeypatch.setattr(Client, "login", lambda self, **kwargs: True)
    monkeypatch.setattr(Client, "get_settings", lambda self: session)

    outcome = login_via_gateway(device_settings)
    assert outcome.status == "ok"
    assert outcome.session == session


def test_health_maps_session_invalid(monkeypatch, device_settings):
    def invalid(self):
        raise LoginRequired()

    monkeypatch.setattr(Client, "account_info", invalid)
    outcome = InstagrapiGateway().health(
        username="conta", proxy=None, session={"cookies": {}}
    )
    assert outcome.status == "invalid"


def test_health_maps_unavailable(monkeypatch, device_settings):
    def unavailable(self):
        raise ClientConnectionError()

    monkeypatch.setattr(Client, "account_info", unavailable)
    outcome = InstagrapiGateway().health(
        username="conta", proxy=None, session={"cookies": {}}
    )
    assert outcome.status == "unavailable"


def test_logout_is_best_effort(monkeypatch, device_settings):
    def fail(self):
        raise ClientError("offline")

    monkeypatch.setattr(Client, "logout", fail)
    # Não propaga erro de rede no logout.
    InstagrapiGateway().logout(
        username="conta", proxy=None, session={"cookies": {}}
    )
