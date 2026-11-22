from tests.helpers import bearer, create_account, register
from tests.test_jobs import enqueue, get_job, login_account, run_next

PREFIXES = {
    "image/jpeg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/webp": b"RIFF\x00\x00\x00\x00WEBP",
    "video/mp4": b"\x00\x00\x00\x18ftypmp42",
    "video/quicktime": b"\x00\x00\x00\x14ftypqt  ",
}


def fake_media(kind: str = "image/jpeg", extra: bytes = b"-fake") -> bytes:
    return PREFIXES.get(kind, b"") + extra


def upload(client, tokens, *, filename="foto.jpg", content=None, kind="image/jpeg"):
    if content is None:
        content = fake_media(kind)
    return client.post(
        "/v1/uploads",
        files={"file": (filename, content, kind)},
        headers=bearer(tokens),
    )


def test_upload_saves_file_and_validates_type(client, media_storage):
    tokens = register(client)
    content = fake_media()
    response = upload(client, tokens, content=content)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["storage_key"].startswith("uploads/")
    assert body["content_type"] == "image/jpeg"
    assert body["size_bytes"] == len(content)
    assert media_storage.path(body["storage_key"]).is_file()

    invalid = upload(client, tokens, filename="x.txt", kind="text/plain")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_upload_type"

    empty = upload(client, tokens, content=b"")
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "empty_upload"

    spoofed = upload(client, tokens, content=b"nao-e-imagem")
    assert spoofed.status_code == 422
    assert spoofed.json()["error"]["code"] == "invalid_upload_content"


def test_publish_photo_uses_uploaded_file(client, worker, ig_gateway):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    uploaded = upload(client, tokens).json()

    job = enqueue(
        client,
        tokens,
        account["id"],
        "publish.photo",
        {"storage_key": uploaded["storage_key"], "caption": "legal #teste"},
    ).json()
    run_next(worker)

    body = get_job(client, tokens, job["id"])
    assert body["status"] == "succeeded", body
    assert body["result"]["publish_state"] == "succeeded"
    assert body["result"]["media_pk"] == ig_gateway.published_media_pk
    call = ig_gateway.publish_calls[-1]
    assert call["action"] == "photo"
    assert call["caption"] == "legal #teste"
    assert call["path"].read_bytes() == fake_media()
    assert call["session"] is not None


def test_publish_timeout_is_ambiguous_and_never_duplicates(
    client, worker, ig_gateway
):
    from app.services.ig_gateway import IgUnavailableError

    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    uploaded = upload(client, tokens).json()
    ig_gateway.publish_error = IgUnavailableError()

    first = enqueue(
        client,
        tokens,
        account["id"],
        "publish.photo",
        {"storage_key": uploaded["storage_key"], "caption": "uma vez"},
        idempotency_key="publish-1",
    )
    assert first.status_code == 202
    job = first.json()
    run_next(worker)

    failed = get_job(client, tokens, job["id"])
    assert failed["status"] == "failed"
    assert failed["error_code"] == "ambiguous_publish"
    assert failed["attempts"] == 1
    assert len(ig_gateway.publish_calls) == 1

    # Não há retry automático: a próxima rodada não pega o job.
    assert worker.claim() is None

    replay = enqueue(
        client,
        tokens,
        account["id"],
        "publish.photo",
        {"storage_key": uploaded["storage_key"], "caption": "uma vez"},
        idempotency_key="publish-1",
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == job["id"]
    assert replay.json()["status"] == "failed"
    assert len(ig_gateway.publish_calls) == 1


def test_publish_variants_reach_gateway(client, worker, ig_gateway):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])

    photo = upload(client, tokens, filename="a.jpg").json()
    photo2 = upload(client, tokens, filename="b.png", kind="image/png").json()
    video = upload(
        client,
        tokens,
        filename="c.mp4",
        content=fake_media("video/mp4"),
        kind="video/mp4",
    ).json()
    thumb = upload(client, tokens, filename="thumb.webp", kind="image/webp").json()

    cases = [
        ("publish.video", {"storage_key": video["storage_key"], "thumbnail_key": thumb["storage_key"]}),
        ("publish.reel", {"storage_key": video["storage_key"]}),
        (
            "publish.album",
            {"storage_keys": [photo["storage_key"], photo2["storage_key"]]},
        ),
        ("publish.story", {"storage_key": photo["storage_key"], "kind": "photo"}),
        ("publish.story", {"storage_key": video["storage_key"], "kind": "video"}),
    ]
    for index, (job_type, payload) in enumerate(cases):
        created = enqueue(client, tokens, account["id"], job_type, payload)
        assert created.status_code == 202, created.text
        run_next(worker)
        body = get_job(client, tokens, created.json()["id"])
        assert body["status"] == "succeeded", (index, body)

    kinds = [call["action"] for call in ig_gateway.publish_calls]
    assert kinds == ["video", "reel", "album", "story", "story"]
    assert ig_gateway.publish_calls[0]["thumbnail"].suffix == ".webp"
    assert len(ig_gateway.publish_calls[2]["paths"]) == 2


def test_publish_payload_rejects_path_traversal_and_bad_types(client, worker):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])

    traversal = enqueue(
        client,
        tokens,
        account["id"],
        "publish.photo",
        {"storage_key": "../segredo.jpg"},
    )
    assert traversal.status_code == 422
    assert traversal.json()["error"]["code"] == "invalid_job_payload"

    photo = upload(client, tokens).json()
    wrong = enqueue(
        client,
        tokens,
        account["id"],
        "publish.video",
        {"storage_key": photo["storage_key"]},
    )
    assert wrong.status_code == 202
    run_next(worker)
    body = get_job(client, tokens, wrong.json()["id"])
    assert body["status"] == "failed"
    assert body["error_code"] == "invalid_upload_type"
