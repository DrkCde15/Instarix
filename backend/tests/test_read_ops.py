from pydantic import HttpUrl

from tests.helpers import bearer, create_account, register
from tests.test_jobs import enqueue, get_job, login_account, run_next


def test_media_list_is_cached_after_job(client, worker, ig_gateway):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])

    missing = client.get(
        f"/v1/accounts/{account['id']}/media", headers=bearer(tokens)
    )
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "media_not_cached"

    ig_gateway.media_items = [
        {"pk": "111", "media_type": 1, "caption": "primeiro"},
        {"pk": "222", "media_type": 2, "caption": None},
    ]
    job = enqueue(
        client, tokens, account["id"], "media.list", {"amount": 2}
    ).json()
    run_next(worker)

    assert get_job(client, tokens, job["id"])["status"] == "succeeded"
    cached = client.get(
        f"/v1/accounts/{account['id']}/media", headers=bearer(tokens)
    )
    assert cached.status_code == 200, cached.text
    body = cached.json()
    assert body["job_id"] == job["id"]
    assert body["username"] == "conta_teste"
    assert [item["pk"] for item in body["items"]] == ["111", "222"]
    assert body["cached_at"] is not None

    call = ig_gateway.media_list_calls[-1]
    assert call["username"] == "conta_teste"
    assert call["amount"] == 2
    assert call["proxy"] is None
    assert call["session"] is not None


def test_media_list_normalizes_non_json_values(client, worker, ig_gateway):
    """HttpUrl do instagrapi não pode quebrar o commit do resultado."""
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])

    url = "https://example.com/thumbnail.jpg"
    ig_gateway.media_items = [
        {
            "pk": "333",
            "media_type": 1,
            "caption": "com miniatura",
            "thumbnail_url": HttpUrl(url),
        }
    ]
    job = enqueue(
        client, tokens, account["id"], "media.list", {"amount": 1}
    ).json()
    run_next(worker)

    finalized = get_job(client, tokens, job["id"])
    assert finalized["status"] == "succeeded"
    assert finalized["result"]["items"][0]["thumbnail_url"] == url

    cached = client.get(
        f"/v1/accounts/{account['id']}/media", headers=bearer(tokens)
    )
    assert cached.status_code == 200, cached.text
    assert cached.json()["items"][0]["thumbnail_url"] == url


def test_media_cache_is_tenant_isolated(client, worker):
    alice = register(client, email="alice@example.com", tenant_name="Alice Co")
    bob = register(client, email="bob@example.com", tenant_name="Bob Co")
    account = create_account(client, alice)
    login_account(client, alice, account["id"])
    enqueue(client, alice, account["id"]).json()
    run_next(worker)

    assert (
        client.get(
            f"/v1/accounts/{account['id']}/media", headers=bearer(bob)
        ).status_code
        == 404
    )


def test_media_download_creates_asset_and_serves_file(
    client, worker, ig_gateway, media_storage
):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])

    job = enqueue(
        client,
        tokens,
        account["id"],
        "media.download",
        {"media_pk": "987654321", "kinds": ["photo"]},
    ).json()
    run_next(worker)

    result = get_job(client, tokens, job["id"])["result"]
    assert result["cached"] is False
    assert len(result["assets"]) == 1
    asset = result["assets"][0]
    assert asset["kind"] == "photo"
    assert asset["media_pk"] == "987654321"
    assert asset["content_type"] == "image/jpeg"
    assert asset["size_bytes"] == len("conteudo-photo")

    download = client.get(f"/v1/media/{asset['id']}", headers=bearer(tokens))
    assert download.status_code == 200, download.text
    assert download.content == b"conteudo-photo"
    assert download.headers["content-type"] == "image/jpeg"
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["cache-control"] == "private, no-store"
    assert "attachment" in download.headers["content-disposition"]

    # Reenfileirar a mesma mídia não baixa de novo.
    enqueue(
        client,
        tokens,
        account["id"],
        "media.download",
        {"media_pk": "987654321", "kinds": ["photo"]},
    )
    run_next(worker)
    assert len(ig_gateway.download_calls) == 1

    bob = register(client, email="bob@example.com", tenant_name="Bob Co")
    assert (
        client.get(f"/v1/media/{asset['id']}", headers=bearer(bob)).status_code
        == 404
    )


def test_insights_sync_creates_snapshot(client, worker, ig_gateway):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])

    missing = client.get(
        f"/v1/accounts/{account['id']}/insights", headers=bearer(tokens)
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "insights_not_found"

    ig_gateway.insights_data = {
        "reach": 1234,
        "profile_views": 56,
        "audience": {"pt_BR": 0.8},
    }
    synced = client.post(
        f"/v1/accounts/{account['id']}/insights/sync", headers=bearer(tokens)
    )
    assert synced.status_code == 202, synced.text
    job = synced.json()
    assert job["type"] == "insights.account"

    run_next(worker)

    job_body = get_job(client, tokens, job["id"])
    assert job_body["status"] == "succeeded"
    snapshot = client.get(
        f"/v1/accounts/{account['id']}/insights", headers=bearer(tokens)
    )
    assert snapshot.status_code == 200, snapshot.text
    body = snapshot.json()
    assert body["id"] == job_body["result"]["snapshot_id"]
    assert body["data"] == ig_gateway.insights_data
    assert body["captured_at"] is not None


def test_insights_sync_requires_jobs_write(client):
    tokens = register(client)
    account = create_account(client, tokens)
    key = client.post(
        "/v1/api-keys",
        json={"name": "leitura", "scopes": ["accounts:read"]},
        headers=bearer(tokens),
    ).json()

    denied = client.post(
        f"/v1/accounts/{account['id']}/insights/sync",
        headers={"X-API-Key": key["key"]},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "insufficient_permission"
