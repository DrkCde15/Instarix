import os
import socket
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.time import utcnow
from app.db.models import Job
from app.services.ig_gateway import HealthOutcome, IgAuthError, IgUnavailableError
from app.workers.worker import JobWorker
from tests.helpers import bearer, create_account, register


def login_account(client, tokens, account_id):
    response = client.post(f"/v1/accounts/{account_id}/login", headers=bearer(tokens))
    assert response.status_code == 200, response.text
    return response.json()


def enqueue(
    client,
    tokens,
    account_id,
    job_type="media.list",
    payload=None,
    *,
    priority=5,
    idempotency_key=None,
):
    body = {"type": job_type, "payload": payload or {}, "priority": priority}
    if idempotency_key is not None:
        body["idempotency_key"] = idempotency_key
    return client.post(
        f"/v1/accounts/{account_id}/jobs", json=body, headers=bearer(tokens)
    )


def get_job(client, tokens, job_id):
    response = client.get(f"/v1/jobs/{job_id}", headers=bearer(tokens))
    assert response.status_code == 200, response.text
    return response.json()


def run_next(worker: JobWorker):
    job = worker.claim()
    assert job is not None
    assert worker.execute(job.id) is True
    return job


def test_create_list_get_and_cancel_job(client):
    tokens = register(client)
    account = create_account(client, tokens)

    created = enqueue(
        client, tokens, account["id"], "media.list", {"amount": 5}, priority=3
    )
    assert created.status_code == 202, created.text
    assert created.headers["Location"] == f"/v1/jobs/{created.json()['id']}"
    body = created.json()
    assert body["status"] == "queued"
    assert body["type"] == "media.list"
    assert body["payload"] == {"username": None, "amount": 5}
    assert body["priority"] == 3
    assert body["attempts"] == 0
    assert body["max_attempts"] == 3
    assert body["result"] is None

    listed = client.get("/v1/jobs", headers=bearer(tokens))
    assert listed.status_code == 200
    page = listed.json()
    assert [item["id"] for item in page["items"]] == [body["id"]]
    assert page["next_cursor"] is None

    fetched = get_job(client, tokens, body["id"])
    assert fetched["id"] == body["id"]

    canceled = client.post(f"/v1/jobs/{body['id']}/cancel", headers=bearer(tokens))
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["status"] == "canceled"
    assert canceled.json()["finished_at"] is not None

    again = client.post(f"/v1/jobs/{body['id']}/cancel", headers=bearer(tokens))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "job_not_cancelable"


def test_list_jobs_by_account_with_pagination_and_filters(client):
    tokens = register(client)
    account = create_account(client, tokens, username="conta_a")
    other = create_account(client, tokens, username="conta_b")

    first = enqueue(client, tokens, account["id"], "media.list").json()
    second = enqueue(client, tokens, account["id"], "insights.account").json()
    enqueue(client, tokens, other["id"], "media.list")

    page = client.get(
        f"/v1/accounts/{account['id']}/jobs?limit=1", headers=bearer(tokens)
    )
    assert page.status_code == 200, page.text
    body = page.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == second["id"]
    assert body["next_cursor"] is not None

    next_page = client.get(
        f"/v1/accounts/{account['id']}/jobs?limit=1&cursor={body['next_cursor']}",
        headers=bearer(tokens),
    )
    assert next_page.status_code == 200, next_page.text
    assert [item["id"] for item in next_page.json()["items"]] == [first["id"]]
    assert next_page.json()["next_cursor"] is None

    filtered = client.get(
        f"/v1/accounts/{account['id']}/jobs?type=media.list",
        headers=bearer(tokens),
    )
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["items"]] == [first["id"]]


def test_list_jobs_by_account_is_tenant_isolated(client):
    alice = register(client, email="alice@example.com", tenant_name="Alice Co")
    bob = register(client, email="bob@example.com", tenant_name="Bob Co")
    account = create_account(client, alice)
    enqueue(client, alice, account["id"])

    response = client.get(
        f"/v1/accounts/{account['id']}/jobs", headers=bearer(bob)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "account_not_found"


def test_idempotency_key_replays_the_same_job(client):
    tokens = register(client)
    account = create_account(client, tokens)

    first = enqueue(
        client, tokens, account["id"], "insights.account", idempotency_key="sync-1"
    )
    assert first.status_code == 202, first.text
    second = enqueue(
        client, tokens, account["id"], "insights.account", idempotency_key="sync-1"
    )
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    assert second.headers["Location"] == f"/v1/jobs/{first.json()['id']}"

    page = client.get("/v1/jobs", headers=bearer(tokens)).json()
    assert len(page["items"]) == 1


def test_invalid_jobs_are_rejected(client):
    tokens = register(client)
    account = create_account(client, tokens)

    unknown = enqueue(client, tokens, account["id"], "media.publish")
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "invalid_job_type"

    bad_payload = enqueue(
        client, tokens, account["id"], "media.download", {"media_pk": "abc"}
    )
    assert bad_payload.status_code == 422
    assert bad_payload.json()["error"]["code"] == "invalid_job_payload"

    extra_field = enqueue(
        client, tokens, account["id"], "media.list", {"limite": 2}
    )
    assert extra_field.status_code == 422
    assert extra_field.json()["error"]["code"] == "invalid_job_payload"

    bad_priority = enqueue(client, tokens, account["id"], priority=99)
    assert bad_priority.status_code == 422


def test_jobs_require_scope_and_are_tenant_isolated(client):
    alice = register(client, email="alice@example.com", tenant_name="Alice Co")
    bob = register(client, email="bob@example.com", tenant_name="Bob Co")
    account = create_account(client, alice)
    job = enqueue(client, alice, account["id"]).json()

    assert client.get(f"/v1/jobs/{job['id']}", headers=bearer(bob)).status_code == 404
    assert client.get("/v1/jobs", headers=bearer(bob)).json()["items"] == []
    assert enqueue(client, bob, account["id"]).status_code == 404
    assert (
        client.post(
            f"/v1/jobs/{job['id']}/cancel", headers=bearer(bob)
        ).status_code
        == 404
    )

    read_key = client.post(
        "/v1/api-keys",
        json={"name": "leitura", "scopes": ["jobs:read"]},
        headers=bearer(alice),
    ).json()
    read_headers = {"X-API-Key": read_key["key"]}
    assert client.get("/v1/jobs", headers=read_headers).status_code == 200
    denied = client.post(
        f"/v1/accounts/{account['id']}/jobs",
        json={"type": "media.list"},
        headers=read_headers,
    )
    assert denied.status_code == 403
    denied_cancel = client.post(f"/v1/jobs/{job['id']}/cancel", headers=read_headers)
    assert denied_cancel.status_code == 403

    write_key = client.post(
        "/v1/api-keys",
        json={"name": "escrita", "scopes": ["jobs:write"]},
        headers=bearer(alice),
    ).json()
    write_headers = {"X-API-Key": write_key["key"]}
    created = client.post(
        f"/v1/accounts/{account['id']}/jobs",
        json={"type": "media.list"},
        headers=write_headers,
    )
    assert created.status_code == 202
    assert client.get("/v1/jobs", headers=write_headers).status_code == 403


def test_worker_serializes_jobs_of_the_same_account(
    client, worker, session_factory, ig_gateway
):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])

    first = enqueue(client, tokens, account["id"], priority=1).json()
    second = enqueue(client, tokens, account["id"], priority=5).json()

    claimed = worker.claim()
    assert claimed is not None and str(claimed.id) == first["id"]

    # Enquanto o primeiro roda, a conta não pode pegar outro job.
    assert worker.claim() is None

    # O índice parcial é a garantia final, mesmo para um escritor fora do worker.
    with session_factory() as db:
        row = db.get(Job, UUID(second["id"]))
        assert row is not None
        row.status = "running"
        row.locked_by = "outro-worker"
        with pytest.raises(IntegrityError):
            db.commit()

    assert worker.execute(claimed.id) is True
    assert get_job(client, tokens, first["id"])["status"] == "succeeded"

    follow_up = worker.claim()
    assert follow_up is not None and str(follow_up.id) == second["id"]
    assert worker.execute(follow_up.id) is True
    assert get_job(client, tokens, second["id"])["status"] == "succeeded"
    assert len(ig_gateway.media_list_calls) == 2


def test_worker_runs_jobs_of_different_accounts_in_parallel(
    client, worker, ig_gateway
):
    tokens = register(client)
    account_a = create_account(client, tokens, username="conta_a")
    account_b = create_account(client, tokens, username="conta_b")
    login_account(client, tokens, account_a["id"])
    login_account(client, tokens, account_b["id"])

    job_a = enqueue(client, tokens, account_a["id"]).json()
    job_b = enqueue(client, tokens, account_b["id"]).json()

    claimed_a = worker.claim()
    assert claimed_a is not None and str(claimed_a.id) == job_a["id"]
    claimed_b = worker.claim()
    assert claimed_b is not None and str(claimed_b.id) == job_b["id"]

    assert worker.execute(claimed_a.id) is True
    assert worker.execute(claimed_b.id) is True
    assert len(ig_gateway.media_list_calls) == 2


def test_worker_retries_transient_errors_with_backoff(
    client, worker, session_factory, ig_gateway
):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    ig_gateway.media_list_error = IgUnavailableError()
    job = enqueue(client, tokens, account["id"]).json()

    run_next(worker)
    after_first = get_job(client, tokens, job["id"])
    assert after_first["status"] == "queued"
    assert after_first["attempts"] == 1
    assert after_first["error_code"] == "instagram_unavailable"
    assert after_first["finished_at"] is None

    for attempt in (2, 3):
        with session_factory() as db:
            row = db.get(Job, UUID(job["id"]))
            assert row is not None
            row.run_after = utcnow() - timedelta(seconds=1)
            db.commit()
        run_next(worker)
        body = get_job(client, tokens, job["id"])
        assert body["attempts"] == attempt
        if attempt == 2:
            assert body["status"] == "queued"

    final = get_job(client, tokens, job["id"])
    assert final["status"] == "failed"
    assert final["error_code"] == "instagram_unavailable"
    assert final["finished_at"] is not None


def test_worker_auth_error_marks_account_needs_reauth(
    client, worker, ig_gateway
):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    ig_gateway.media_list_error = IgAuthError()
    job = enqueue(client, tokens, account["id"]).json()

    run_next(worker)

    failed = get_job(client, tokens, job["id"])
    assert failed["status"] == "failed"
    assert failed["error_code"] == "account_needs_reauth"
    status = client.get(f"/v1/accounts/{account['id']}", headers=bearer(tokens)).json()
    assert status["status"] == "needs_reauth"
    assert status["has_session"] is False


def test_worker_rejects_job_for_inactive_account(client, worker):
    tokens = register(client)
    account = create_account(client, tokens)
    job = enqueue(client, tokens, account["id"]).json()

    run_next(worker)

    body = get_job(client, tokens, job["id"])
    assert body["status"] == "failed"
    assert body["error_code"] == "account_not_active"


def test_worker_health_job_updates_last_health_at(
    client, worker, session_factory
):
    from app.db.models import IgAccount

    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    job = enqueue(client, tokens, account["id"], "account.health").json()

    run_next(worker)

    body = get_job(client, tokens, job["id"])
    assert body["status"] == "succeeded"
    assert body["result"] == {"status": "ok"}
    with session_factory() as db:
        row = db.get(IgAccount, UUID(account["id"]))
        assert row is not None
        assert row.last_health_at is not None


def test_health_job_transient_failure_keeps_session(client, worker, ig_gateway):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    ig_gateway.health_outcome = HealthOutcome("unavailable")
    job = enqueue(client, tokens, account["id"], "account.health").json()

    run_next(worker)

    body = get_job(client, tokens, job["id"])
    assert body["status"] == "queued"
    assert body["error_code"] == "instagram_unavailable"
    status = client.get(f"/v1/accounts/{account['id']}", headers=bearer(tokens)).json()
    assert status["status"] == "active"
    assert status["has_session"] is True


def test_sweeper_recovers_job_from_dead_worker(client, worker, session_factory):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    job = enqueue(client, tokens, account["id"]).json()

    claimed = worker.claim()
    assert claimed is not None
    # Lock recente não é recuperado.
    assert worker.sweep() == 0

    with session_factory() as db:
        row = db.get(Job, UUID(job["id"]))
        assert row is not None
        row.locked_at = utcnow() - timedelta(seconds=3600)
        db.commit()

    assert worker.sweep() == 1
    recovered = get_job(client, tokens, job["id"])
    assert recovered["status"] == "queued"
    assert recovered["error_code"] == "job_worker_lost"
    assert recovered["attempts"] == 1

    reclaimed = worker.claim()
    assert reclaimed is not None and str(reclaimed.id) == job["id"]
    assert reclaimed.attempts == 2

    # Sem tentativas restantes, o sweeper encerra o job em vez de reciclar.
    with session_factory() as db:
        row = db.get(Job, UUID(job["id"]))
        assert row is not None
        row.max_attempts = 2
        row.locked_at = utcnow() - timedelta(seconds=3600)
        db.commit()

    assert worker.sweep() == 1
    lost = get_job(client, tokens, job["id"])
    assert lost["status"] == "failed"
    assert lost["error_code"] == "job_worker_lost"
    assert lost["finished_at"] is not None


def test_startup_recovers_job_owned_by_dead_process(client, worker, session_factory):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    job = enqueue(client, tokens, account["id"]).json()

    with session_factory() as db:
        row = db.get(Job, UUID(job["id"]))
        assert row is not None
        row.status = "running"
        row.attempts = 1
        row.locked_by = f"{socket.gethostname()}:999999:0:deadbeef"
        row.locked_at = utcnow()
        db.commit()

    assert worker.recover_dead_workers() == 1
    recovered = get_job(client, tokens, job["id"])
    assert recovered["status"] == "queued"
    assert recovered["error_code"] == "job_worker_lost"
    assert recovered["attempts"] == 1
    with session_factory() as db:
        row = db.get(Job, UUID(job["id"]))
        assert row is not None
        assert row.locked_by is None
        assert row.locked_at is None


def test_startup_does_not_steal_live_or_foreign_locks(client, worker, session_factory):
    tokens = register(client)
    first = create_account(client, tokens, username="conta_viva")
    second = create_account(client, tokens, username="conta_outro_host")
    login_account(client, tokens, first["id"])
    login_account(client, tokens, second["id"])
    jobs = [
        enqueue(client, tokens, first["id"]).json(),
        enqueue(client, tokens, second["id"]).json(),
    ]
    owners = [
        f"{socket.gethostname()}:{os.getpid()}:0:alive1",
        "outro-host:999999:1:foreign",
    ]

    with session_factory() as db:
        for job, owner in zip(jobs, owners):
            row = db.get(Job, UUID(job["id"]))
            assert row is not None
            row.status = "running"
            row.locked_by = owner
            row.locked_at = utcnow()
        db.commit()

    assert worker.recover_dead_workers() == 0
    for job in jobs:
        assert get_job(client, tokens, job["id"])["status"] == "running"


def test_worker_id_is_isolated_between_instances(
    client, worker, session_factory, ig_gateway, media_storage
):
    from app.core.config import get_settings
    from app.core.crypto import get_cipher

    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    enqueue(client, tokens, account["id"])

    other = JobWorker(
        session_factory=session_factory,
        cipher=get_cipher(),
        gateway=ig_gateway,
        storage=media_storage,
        settings=get_settings(),
        worker_id="outro-worker",
    )
    claimed = worker.claim()
    assert claimed is not None
    # Um worker não executa job preso a outro.
    assert other.execute(claimed.id) is False
