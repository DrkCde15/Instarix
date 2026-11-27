"""Motor de fluxos de automação (MVP).

Um fluxo é um grafo simples: um nó gatilho, condições com saídas
``true``/``false`` e ações. Nesta fase as ações de resposta são simuladas e o
gatilho é manual; a captura de DM/comentário virá depois.
"""

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.crypto import Cipher
from app.core.errors import AppError, not_found
from app.core.time import as_utc, utcnow
from app.db.models import Flow, FlowRun, IgAccount, IgAccountStatus
from app.schemas.flow import FlowCreate, FlowRunCreate, FlowUpdate
from app.schemas.job import JobCreate
from app.services.ig_gateway import IgGateway, IgGatewayError
from app.services.jobs import JobService

MAX_STEPS = 50
NODE_TYPES = frozenset(
    {
        "trigger.manual",
        "condition.keyword",
        "action.reply_dm",
        "action.reply_comment",
        "action.publish",
        "action.schedule_publish",
    }
)
PUBLISH_TYPES = frozenset(
    {
        "publish.photo",
        "publish.video",
        "publish.reel",
        "publish.album",
        "publish.story",
    }
)


class FlowService:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        gateway: IgGateway | None = None,
        cipher: Cipher | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.gateway = gateway
        self.cipher = cipher

    # -- CRUD ------------------------------------------------------------

    def _validate_graph(self, graph: dict[str, Any]) -> dict[str, Any]:
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        ids = [node["id"] for node in nodes]
        if len(ids) != len(set(ids)):
            raise AppError(422, "invalid_flow_graph", "IDs de nó duplicados.")
        unknown = sorted({node["type"] for node in nodes} - NODE_TYPES)
        if unknown:
            raise AppError(
                422, "invalid_flow_graph", f"Tipos de nó desconhecidos: {', '.join(unknown)}."
            )
        known = set(ids)
        for edge in edges:
            if edge["source"] not in known or edge["target"] not in known:
                raise AppError(
                    422, "invalid_flow_graph", "Aresta aponta para nó inexistente."
                )
        return graph

    def _validate_trigger(
        self,
        tenant_id: uuid.UUID,
        trigger_source: str,
        account_id: uuid.UUID | None,
    ) -> None:
        if trigger_source == "manual":
            return
        if account_id is None:
            raise AppError(
                422,
                "flow_account_required",
                "Escolha a conta para consultar DMs ou comentários.",
            )
        account = self.db.scalar(
            select(IgAccount).where(
                IgAccount.id == account_id,
                IgAccount.tenant_id == tenant_id,
                IgAccount.deleted_at.is_(None),
            )
        )
        if account is None:
            raise not_found("account_not_found", "Conta não encontrada.")

    def _account_session(
        self, tenant_id: uuid.UUID, account_id: Any
    ) -> tuple[IgAccount, dict[str, Any], str | None]:
        try:
            account_uuid = uuid.UUID(str(account_id))
        except (ValueError, TypeError):
            raise AppError(422, "invalid_account", "Conta inválida.") from None
        account = self.db.scalar(
            select(IgAccount).where(
                IgAccount.id == account_uuid,
                IgAccount.tenant_id == tenant_id,
                IgAccount.deleted_at.is_(None),
            )
        )
        if account is None:
            raise AppError(422, "invalid_account", "Conta não encontrada.")
        if account.status != IgAccountStatus.ACTIVE or not account.session_enc:
            raise AppError(
                422, "account_unavailable", "A conta precisa estar ativa e com sessão."
            )
        if self.cipher is None:
            raise AppError(422, "missing_cipher", "Cifra de sessão indisponível.")
        try:
            session = self.cipher.decrypt_json(account.session_enc)
            proxy = (
                self.cipher.decrypt(account.proxy_enc) if account.proxy_enc else None
            )
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                422, "invalid_session_payload", "Sessão inválida; faça login novamente."
            ) from exc
        return account, session, proxy

    # -- Polling ---------------------------------------------------------

    def due_polls(self, limit: int = 50) -> list[Flow]:
        now = utcnow()
        candidates = list(
            self.db.scalars(
                select(Flow)
                .where(
                    Flow.enabled.is_(True),
                    Flow.trigger_source.in_(("dm", "comment")),
                    Flow.account_id.is_not(None),
                )
                .limit(limit)
            )
        )
        return [
            flow
            for flow in candidates
            if flow.last_poll_at is None
            or as_utc(flow.last_poll_at)
            + timedelta(seconds=flow.poll_interval_seconds)
            <= now
        ]

    def claim_poll(self, flow: Flow) -> bool:
        cutoff = utcnow() - timedelta(seconds=flow.poll_interval_seconds)
        result = self.db.execute(
            update(Flow)
            .where(
                Flow.id == flow.id,
                or_(Flow.last_poll_at.is_(None), Flow.last_poll_at <= cutoff),
            )
            .values(last_poll_at=utcnow())
            .execution_options(synchronize_session=False)
        )
        self.db.commit()
        return result.rowcount == 1

    def create(
        self,
        tenant_id: uuid.UUID,
        data: FlowCreate,
        user_id: uuid.UUID | None = None,
    ) -> Flow:
        self._validate_trigger(tenant_id, data.trigger_source, data.account_id)
        graph = self._validate_graph(data.graph.model_dump())
        flow = Flow(
            tenant_id=tenant_id,
            name=data.name.strip(),
            description=(data.description or "").strip() or None,
            category=data.category.strip() or "geral",
            enabled=data.enabled,
            graph=graph,
            trigger_source=data.trigger_source,
            account_id=data.account_id,
            poll_interval_seconds=data.poll_interval_seconds,
            created_by=user_id,
        )
        self.db.add(flow)
        self.db.commit()
        return flow

    def list_all(self, tenant_id: uuid.UUID) -> list[Flow]:
        return list(
            self.db.scalars(
                select(Flow)
                .where(Flow.tenant_id == tenant_id)
                .order_by(Flow.created_at.desc())
            )
        )

    def get(self, tenant_id: uuid.UUID, flow_id: uuid.UUID) -> Flow:
        flow = self.db.scalar(
            select(Flow).where(Flow.id == flow_id, Flow.tenant_id == tenant_id)
        )
        if flow is None:
            raise not_found("flow_not_found", "Fluxo não encontrado.")
        return flow

    def update(
        self, tenant_id: uuid.UUID, flow_id: uuid.UUID, data: FlowUpdate
    ) -> Flow:
        flow = self.get(tenant_id, flow_id)
        if data.name is not None:
            flow.name = data.name.strip()
        if data.description is not None:
            flow.description = data.description.strip() or None
        if data.category is not None:
            flow.category = data.category.strip() or "geral"
        if data.enabled is not None:
            flow.enabled = data.enabled
        if data.trigger_source is not None or data.account_id is not None:
            self._validate_trigger(
                flow.tenant_id,
                data.trigger_source or flow.trigger_source,
                data.account_id if data.account_id is not None else flow.account_id,
            )
        if data.trigger_source is not None:
            flow.trigger_source = data.trigger_source
        if data.account_id is not None:
            flow.account_id = data.account_id
        if data.poll_interval_seconds is not None:
            flow.poll_interval_seconds = data.poll_interval_seconds
        if data.graph is not None:
            flow.graph = self._validate_graph(data.graph.model_dump())
        self.db.commit()
        return flow

    def delete(self, tenant_id: uuid.UUID, flow_id: uuid.UUID) -> None:
        flow = self.get(tenant_id, flow_id)
        self.db.delete(flow)
        self.db.commit()

    def runs(
        self, tenant_id: uuid.UUID, flow_id: uuid.UUID, limit: int = 50
    ) -> list[FlowRun]:
        self.get(tenant_id, flow_id)
        return list(
            self.db.scalars(
                select(FlowRun)
                .where(FlowRun.tenant_id == tenant_id, FlowRun.flow_id == flow_id)
                .order_by(FlowRun.created_at.desc())
                .limit(limit)
            )
        )

    def summary(self, tenant_id: uuid.UUID) -> dict[str, Any]:
        flows = list(
            self.db.scalars(select(Flow).where(Flow.tenant_id == tenant_id))
        )
        runs = list(
            self.db.scalars(
                select(FlowRun)
                .where(FlowRun.tenant_id == tenant_id)
                .order_by(FlowRun.created_at.desc())
                .limit(1000)
            )
        )
        flow_names = {flow.id: flow.name for flow in flows}
        runs_by_flow = Counter(run.flow_id for run in runs)
        succeeded = sum(1 for run in runs if run.status == "succeeded")
        with_runs = {run.flow_id for run in runs}

        activity_counts: Counter[str] = Counter(
            as_utc(run.created_at).date().isoformat() for run in runs
        )
        today = utcnow().date()
        activity = [
            {
                "date": (today - timedelta(days=offset)).isoformat(),
                "runs": activity_counts.get(
                    (today - timedelta(days=offset)).isoformat(), 0
                ),
            }
            for offset in range(13, -1, -1)
        ]

        return {
            "total_flows": len(flows),
            "active_flows": sum(1 for flow in flows if flow.enabled),
            "paused_flows": sum(
                1 for flow in flows if not flow.enabled and flow.id in with_runs
            ),
            "draft_flows": sum(
                1 for flow in flows if not flow.enabled and flow.id not in with_runs
            ),
            "total_runs": len(runs),
            "succeeded_runs": succeeded,
            "success_rate": round(succeeded / len(runs) * 100, 1) if runs else 0.0,
            "recent_runs": runs[:8],
            "top_flows": [
                {"flow_id": str(flow_id), "name": flow_names.get(flow_id, "—"), "runs": count}
                for flow_id, count in runs_by_flow.most_common(5)
            ],
            "activity": activity,
        }

    # -- Execução --------------------------------------------------------

    @staticmethod
    def _next_nodes(graph: dict[str, Any], source: str, handle: str) -> list[str]:
        return [
            edge["target"]
            for edge in graph.get("edges", [])
            if edge["source"] == source
            and (edge.get("source_handle") is None or edge["source_handle"] == handle)
        ]

    def _run_node(
        self,
        node: dict[str, Any],
        context: dict[str, Any],
        run: FlowRun,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        node_type = node["type"]
        config = node.get("config") or {}
        step: dict[str, Any] = {
            "node_id": node["id"],
            "type": node_type,
            "status": "ok",
            "detail": {},
        }

        if node_type == "trigger.manual":
            return step

        if node_type == "condition.keyword":
            field = str(config.get("field") or "input_text")
            keyword = str(config.get("keyword") or "").strip().lower()
            mode = str(config.get("mode") or "contains")
            value = str(context.get(field) or "").lower()
            matched = bool(keyword) and (
                keyword in value if mode == "contains" else keyword == value.strip()
            )
            step["detail"] = {
                "field": field,
                "keyword": keyword,
                "matched": matched,
            }
            step["handle"] = "true" if matched else "false"
            return step

        if node_type in {"action.reply_dm", "action.reply_comment"}:
            message = str(config.get("message") or "")
            account_id = config.get("account_id") or context.get("account_id")
            step["handle"] = "out"
            simulated = {
                "message": message,
                "recipient_hint": context.get("subscriber_id"),
                "simulated": True,
            }

            if node_type == "action.reply_dm":
                thread_id = config.get("thread_id") or context.get("thread_id")
                if not (thread_id and account_id) or self.gateway is None:
                    step["detail"] = simulated
                    return step
                try:
                    _, session, proxy = self._account_session(tenant_id, account_id)
                    self.gateway.direct_answer(
                        thread_id=str(thread_id),
                        message=message,
                        proxy=proxy,
                        session=session,
                    )
                except (AppError, IgGatewayError) as exc:
                    step.update(
                        status="error",
                        detail={
                            "reason": getattr(exc, "code", "reply_failed"),
                            "message": getattr(exc, "message", str(exc)),
                        },
                    )
                    return step
                step["detail"] = {
                    "thread_id": str(thread_id),
                    "message": message,
                    "sent": True,
                }
                return step

            media_pk = config.get("media_pk") or context.get("media_pk")
            comment_id = config.get("comment_id") or context.get("comment_id")
            if not (media_pk and comment_id and account_id) or self.gateway is None:
                step["detail"] = simulated
                return step
            try:
                _, session, proxy = self._account_session(tenant_id, account_id)
                self.gateway.reply_comment(
                    media_pk=str(media_pk),
                    comment_id=str(comment_id),
                    message=message,
                    proxy=proxy,
                    session=session,
                )
            except (AppError, IgGatewayError) as exc:
                step.update(
                    status="error",
                    detail={
                        "reason": getattr(exc, "code", "reply_failed"),
                        "message": getattr(exc, "message", str(exc)),
                    },
                )
                return step
            step["detail"] = {
                "media_pk": str(media_pk),
                "comment_id": str(comment_id),
                "message": message,
                "sent": True,
            }
            return step

        if node_type in {"action.publish", "action.schedule_publish"}:
            run_after: datetime | None = None
            raw_schedule = config.get("run_after")
            if raw_schedule:
                try:
                    run_after = datetime.fromisoformat(str(raw_schedule).replace("Z", "+00:00"))
                except ValueError:
                    step.update(
                        status="error", detail={"reason": "invalid_schedule"}
                    )
                    return step
                if run_after is not None and run_after.tzinfo is None:
                    run_after = run_after.replace(tzinfo=UTC)
            elif node_type == "action.schedule_publish":
                step.update(status="error", detail={"reason": "missing_schedule"})
                return step

            job_type = str(config.get("type") or "publish.photo")
            if job_type not in PUBLISH_TYPES:
                step.update(
                    status="error",
                    detail={"reason": "invalid_publish_type", "type": job_type},
                )
                return step
            account_id = config.get("account_id") or context.get("account_id")
            try:
                account_uuid = uuid.UUID(str(account_id))
            except (ValueError, TypeError):
                step.update(status="error", detail={"reason": "invalid_account"})
                return step
            payload: dict[str, Any] = {
                "caption": str(config.get("caption") or context.get("caption") or "")
            }
            if job_type == "publish.album":
                payload["storage_keys"] = config.get("storage_keys") or []
            else:
                payload["storage_key"] = str(config.get("storage_key") or "")
                if config.get("thumbnail_key"):
                    payload["thumbnail_key"] = str(config["thumbnail_key"])
            try:
                result = JobService(self.db, self.settings).create(
                    tenant_id,
                    account_uuid,
                    JobCreate(
                        type=job_type,
                        payload=payload,
                        idempotency_key=f"flow:{run.id}:{node['id']}",
                        run_after=run_after,
                    ),
                    user_id,
                )
            except AppError as exc:
                step.update(status="error", detail={"reason": exc.code, "message": exc.message})
                return step
            step["detail"] = {
                "job_id": str(result.job.id),
                "type": job_type,
                "created": result.created,
                "scheduled_for": run_after.isoformat() if run_after else None,
            }
            step["handle"] = "out"
            return step

        step.update(status="error", detail={"reason": "unsupported_node"})
        return step

    def run(
        self,
        tenant_id: uuid.UUID,
        flow_id: uuid.UUID,
        data: FlowRunCreate,
        user_id: uuid.UUID | None = None,
    ) -> FlowRun:
        flow = self.get(tenant_id, flow_id)
        run = FlowRun(
            tenant_id=tenant_id,
            flow_id=flow.id,
            status="running",
            trigger=data.trigger,
            context=data.context,
            steps=[],
        )
        self.db.add(run)
        self.db.commit()

        nodes = {node["id"]: node for node in flow.graph.get("nodes", [])}
        triggers = [node for node in nodes.values() if node["type"].startswith("trigger.")]
        steps: list[dict[str, Any]] = []
        error: tuple[str, str] | None = None

        if not triggers:
            error = ("no_trigger", "O fluxo não tem nó gatilho.")
        else:
            current = triggers[0]["id"]
            for _ in range(MAX_STEPS):
                node = nodes.get(current)
                if node is None:
                    break
                step = self._run_node(node, dict(data.context), run, tenant_id, user_id)
                steps.append(step)
                if step["status"] == "error":
                    error = ("step_failed", f"Nó {node['id']} falhou.")
                    break
                next_nodes = self._next_nodes(
                    flow.graph, current, str(step.get("handle", "out"))
                )
                if not next_nodes:
                    break
                current = next_nodes[0]

        run.steps = steps
        if error:
            run.status = "failed"
            run.error_code, run.error_message = error
        else:
            run.status = "succeeded"
        run.finished_at = utcnow()
        self.db.commit()
        return run
