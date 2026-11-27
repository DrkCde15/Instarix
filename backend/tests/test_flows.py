from datetime import timedelta

from app.core.time import utcnow
from app.db.models import Flow

from tests.helpers import bearer, create_account, register
from tests.test_jobs import get_job, login_account

GRAPH = {
    "nodes": [
        {"id": "start", "type": "trigger.manual", "config": {}},
        {
            "id": "check",
            "type": "condition.keyword",
            "config": {"field": "input_text", "keyword": "link", "mode": "contains"},
        },
        {
            "id": "reply",
            "type": "action.reply_dm",
            "config": {"message": "Segue o link: https://exemplo.com"},
        },
        {
            "id": "other",
            "type": "action.reply_comment",
            "config": {"message": "Oi!Como podemos ajudar?"},
        },
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "check"},
        {"id": "e2", "source": "check", "target": "reply", "source_handle": "true"},
        {"id": "e3", "source": "check", "target": "other", "source_handle": "false"},
    ],
}


def create_flow(client, tokens, *, name="Fluxo de teste", graph=None):
    response = client.post(
        "/v1/flows",
        headers=bearer(tokens),
        json={"name": name, "graph": graph or GRAPH},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_flow_summary_uses_real_runs(client):
    tokens = register(client)
    flow = create_flow(client, tokens)
    client.post(
        f"/v1/flows/{flow['id']}/run",
        headers=bearer(tokens),
        json={"context": {"input_text": "oi"}},
    )

    summary = client.get("/v1/flows/summary", headers=bearer(tokens))
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["total_flows"] == 1
    assert body["active_flows"] == 1
    assert body["total_runs"] == 1
    assert body["succeeded_runs"] == 1
    assert body["success_rate"] == 100.0
    assert len(body["recent_runs"]) == 1
    assert body["top_flows"][0]["flow_id"] == flow["id"]
    assert len(body["activity"]) == 14
    assert sum(day["runs"] for day in body["activity"]) == 1

    other = register(client, email="outro@example.com", tenant_name="Outro")
    other_body = client.get("/v1/flows/summary", headers=bearer(other)).json()
    assert other_body["total_flows"] == 0
    assert other_body["total_runs"] == 0


def test_flow_description_and_category_are_persisted(client):
    tokens = register(client)
    created = client.post(
        "/v1/flows",
        headers=bearer(tokens),
        json={
            "name": "Fluxo categorizado",
            "description": "Atendimento inicial",
            "category": "atendimento",
            "graph": GRAPH,
        },
    ).json()
    assert created["description"] == "Atendimento inicial"
    assert created["category"] == "atendimento"

    updated = client.patch(
        f"/v1/flows/{created['id']}",
        headers=bearer(tokens),
        json={"description": "Novo texto", "category": "conteudo"},
    ).json()
    assert updated["description"] == "Novo texto"
    assert updated["category"] == "conteudo"


def test_flow_crud_and_tenant_isolation(client):
    alice = register(client)
    bob = register(client, email="bob@example.com", tenant_name="Bob")
    flow = create_flow(client, alice)

    assert client.get("/v1/flows", headers=bearer(alice)).json()[0]["id"] == flow["id"]
    assert client.get("/v1/flows", headers=bearer(bob)).json() == []
    assert (
        client.get(f"/v1/flows/{flow['id']}", headers=bearer(bob)).status_code == 404
    )

    updated = client.patch(
        f"/v1/flows/{flow['id']}",
        headers=bearer(alice),
        json={"name": "Novo nome", "enabled": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Novo nome"
    assert updated.json()["enabled"] is False

    assert (
        client.delete(f"/v1/flows/{flow['id']}", headers=bearer(bob)).status_code == 404
    )
    assert (
        client.delete(f"/v1/flows/{flow['id']}", headers=bearer(alice)).status_code == 204
    )
    assert client.get("/v1/flows", headers=bearer(alice)).json() == []


def test_manual_run_follows_condition_branch(client):
    tokens = register(client)
    flow = create_flow(client, tokens)

    matched = client.post(
        f"/v1/flows/{flow['id']}/run",
        headers=bearer(tokens),
        json={"trigger": "manual", "context": {"input_text": "quero o LINK"}},
    )
    assert matched.status_code == 200, matched.text
    body = matched.json()
    assert body["status"] == "succeeded"
    assert [step["node_id"] for step in body["steps"]] == ["start", "check", "reply"]
    assert body["steps"][1]["detail"]["matched"] is True
    assert body["steps"][2]["detail"]["simulated"] is True

    other = client.post(
        f"/v1/flows/{flow['id']}/run",
        headers=bearer(tokens),
        json={"trigger": "manual", "context": {"input_text": "oi"}},
    ).json()
    assert [step["node_id"] for step in other["steps"]] == ["start", "check", "other"]

    runs = client.get(f"/v1/flows/{flow['id']}/runs", headers=bearer(tokens)).json()
    assert len(runs) == 2
    assert {run["status"] for run in runs} == {"succeeded"}


def test_publish_action_enqueues_one_job_per_run(client):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    graph = {
        "nodes": [
            {"id": "start", "type": "trigger.manual", "config": {}},
            {
                "id": "publish",
                "type": "action.publish",
                "config": {
                    "account_id": account["id"],
                    "type": "publish.photo",
                    "storage_key": "tenant/conta/foto.jpg",
                    "caption": "publicado pelo fluxo",
                },
            },
        ],
        "edges": [{"id": "e1", "source": "start", "target": "publish"}],
    }
    flow = create_flow(client, tokens, graph=graph)

    first = client.post(
        f"/v1/flows/{flow['id']}/run",
        headers=bearer(tokens),
        json={"context": {}},
    ).json()
    assert first["status"] == "succeeded"
    job_id = first["steps"][1]["detail"]["job_id"]
    assert first["steps"][1]["detail"]["created"] is True

    job = get_job(client, tokens, job_id)
    assert job["type"] == "publish.photo"
    assert job["payload"]["caption"] == "publicado pelo fluxo"

    second = client.post(
        f"/v1/flows/{flow['id']}/run",
        headers=bearer(tokens),
        json={"context": {}},
    ).json()
    # Cada execução do fluxo é uma publicação nova; a chave de idempotência
    # inclui o run_id, então repetir o mesmo nó dentro de uma corrida não duplica.
    assert second["steps"][1]["detail"]["job_id"] != job_id
    assert second["steps"][1]["detail"]["created"] is True


def test_schedule_publish_node_sets_run_after(client):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    scheduled = utcnow() + timedelta(hours=1)
    graph = {
        "nodes": [
            {"id": "start", "type": "trigger.manual", "config": {}},
            {
                "id": "schedule",
                "type": "action.schedule_publish",
                "config": {
                    "account_id": account["id"],
                    "type": "publish.photo",
                    "storage_key": "tenant/conta/foto.jpg",
                    "run_after": scheduled.isoformat(),
                },
            },
        ],
        "edges": [{"id": "e1", "source": "start", "target": "schedule"}],
    }
    flow = create_flow(client, tokens, graph=graph)

    result = client.post(
        f"/v1/flows/{flow['id']}/run", headers=bearer(tokens), json={"context": {}}
    ).json()
    assert result["status"] == "succeeded"
    assert result["steps"][1]["detail"]["scheduled_for"] == scheduled.isoformat()

    job = get_job(client, tokens, result["steps"][1]["detail"]["job_id"])
    assert job["type"] == "publish.photo"
    assert job["run_after"].startswith(scheduled.strftime("%Y-%m-%dT%H:%M:%S"))


def test_invalid_graph_is_rejected(client):
    tokens = register(client)
    bad = {
        "nodes": [
            {"id": "a", "type": "trigger.manual"},
            {"id": "b", "type": "action.nao_existe"},
        ],
        "edges": [],
    }
    response = client.post(
        "/v1/flows", headers=bearer(tokens), json={"name": "Invalido", "graph": bad}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_flow_graph"


REPLY_GRAPH = {
    "nodes": [
        {"id": "start", "type": "trigger.manual", "config": {}},
        {
            "id": "check",
            "type": "condition.keyword",
            "config": {"keyword": "link"},
        },
        {"id": "answer", "type": "action.reply_dm", "config": {"message": "Aqui: link"}},
        {"id": "other", "type": "action.reply_comment", "config": {"message": "Oi!"}},
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "check"},
        {"id": "e2", "source": "check", "target": "answer", "source_handle": "true"},
        {"id": "e3", "source": "check", "target": "other", "source_handle": "false"},
    ],
}


def create_polling_flow(client, tokens, account_id, source, **extra):
    body = {
        "name": f"Fluxo {source}",
        "graph": REPLY_GRAPH,
        "trigger_source": source,
        "account_id": account_id,
        "poll_interval_seconds": 30,
    }
    body.update(extra)
    response = client.post("/v1/flows", headers=bearer(tokens), json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_dm_polling_enqueues_event_and_sends_reply(client, worker, ig_gateway):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    ig_gateway.direct_messages = [
        {
            "message_id": "m2",
            "thread_id": "t1",
            "user_id": "u1",
            "text": "quero o link",
        }
    ]
    create_polling_flow(client, tokens, account["id"], "dm")

    assert worker.poll_flow_triggers() == 1
    jobs = client.get(
        "/v1/jobs?type=flow.event", headers=bearer(tokens)
    ).json()["items"]
    assert len(jobs) == 1
    assert jobs[0]["payload"]["context"]["thread_id"] == "t1"
    assert jobs[0]["payload"]["context"]["input_text"] == "quero o link"

    worker.run_available(limit=10)

    assert len(ig_gateway.direct_calls) == 1
    assert ig_gateway.direct_calls[0]["thread_id"] == "t1"
    assert "link" in ig_gateway.direct_calls[0]["message"]


def test_comment_polling_replies_to_comment(client, worker, ig_gateway):
    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    ig_gateway.comment_items = [
        {
            "comment_id": "c1",
            "media_pk": "555",
            "user_id": "u2",
            "username": "ana",
            "text": "oi tudo bem",
        }
    ]
    create_polling_flow(client, tokens, account["id"], "comment")

    assert worker.poll_flow_triggers() == 1
    worker.run_available(limit=10)

    assert len(ig_gateway.comment_calls) == 1
    assert ig_gateway.comment_calls[0]["media_pk"] == "555"
    assert ig_gateway.comment_calls[0]["comment_id"] == "c1"


def test_polling_deduplicates_seen_messages(client, worker, session_factory, ig_gateway):
    import uuid

    tokens = register(client)
    account = create_account(client, tokens)
    login_account(client, tokens, account["id"])
    ig_gateway.direct_messages = [
        {"message_id": "m1", "thread_id": "t1", "user_id": "u1", "text": "oi"}
    ]
    flow = create_polling_flow(client, tokens, account["id"], "dm")

    assert worker.poll_flow_triggers() == 1
    with session_factory() as db:
        row = db.get(Flow, uuid.UUID(flow["id"]))
        assert row is not None
        assert row.last_seen_id == "m1"
        row.last_poll_at = utcnow() - timedelta(seconds=120)
        db.commit()

    assert worker.poll_flow_triggers() == 0
    jobs = client.get("/v1/jobs", headers=bearer(tokens)).json()["items"]
    assert len(jobs) == 1
