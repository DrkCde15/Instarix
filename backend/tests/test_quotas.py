from uuid import UUID

import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import Tenant
from app.schemas.job import JobCreate
from app.services.jobs import JobService
from tests.helpers import bearer, create_account, register


def test_account_quota_by_plan_and_usage(client, session_factory):
    tokens = register(client)
    for index in range(3):
        create_account(client, tokens, username=f"conta_{index}")

    blocked = client.post(
        "/v1/accounts",
        json={"label": "x", "username": "conta_3", "password": "senha-instagram"},
        headers=bearer(tokens),
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "quota_exceeded"

    usage = client.get("/v1/usage", headers=bearer(tokens)).json()
    assert usage == {
        "plan": "free",
        "accounts_used": 3,
        "accounts_limit": 3,
        "jobs_today_used": 0,
        "jobs_today_limit": 100,
    }

    with session_factory() as db:
        tenant = db.query(Tenant).one()
        tenant.plan = "pro"
        db.commit()

    allowed = create_account(client, tokens, username="conta_3")
    assert allowed["id"]
    usage = client.get("/v1/usage", headers=bearer(tokens)).json()
    assert usage["plan"] == "pro"
    assert usage["accounts_used"] == 4
    assert usage["accounts_limit"] == 25


def test_job_daily_quota_and_idempotent_replay(client, session_factory):
    tokens = register(client)
    account = create_account(client, tokens)
    me = client.get("/v1/me", headers=bearer(tokens)).json()

    first = client.post(
        f"/v1/accounts/{account['id']}/jobs",
        json={"type": "media.list"},
        headers=bearer(tokens),
    )
    assert first.status_code == 202

    replay = client.post(
        f"/v1/accounts/{account['id']}/jobs",
        json={"type": "media.list", "idempotency_key": "replay-quota"},
        headers=bearer(tokens),
    )
    assert replay.status_code == 202

    settings = get_settings().model_copy(update={"quota_free_jobs_per_day": 1})
    with session_factory() as db:
        service = JobService(db, settings)

        # Replay por idempotência é resolvido antes da quota.
        existing = service.create(
            UUID(me["tenant_id"]),
            UUID(account["id"]),
            JobCreate(type="media.list", idempotency_key="replay-quota"),
            None,
        )
        assert existing.created is False

        with pytest.raises(AppError) as exc:
            service.create(
                UUID(me["tenant_id"]),
                UUID(account["id"]),
                JobCreate(type="media.list"),
                None,
            )
    assert exc.value.status_code == 429
    assert exc.value.code == "quota_exceeded"

    usage = client.get("/v1/usage", headers=bearer(tokens)).json()
    assert usage["jobs_today_used"] == 2
    assert usage["jobs_today_limit"] == 100
