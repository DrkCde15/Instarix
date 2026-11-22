"""Contexto de tenant para Row-Level Security (opt-in no PostgreSQL).

As policies ficam em scripts/enable_rls.py. Quando ``RLS_ENABLED=true``, toda
sessão da API recebe ``app.tenant_id`` na transação corrente; o worker deve usar
um role com BYPASSRLS, pois ele precisa enxergar jobs de todos os tenants.
"""

from contextvars import ContextVar

from sqlalchemy import event, text
from sqlalchemy.orm import Session

_current_tenant: ContextVar[str | None] = ContextVar(
    "instarix_current_tenant", default=None
)


def current_tenant() -> str | None:
    return _current_tenant.get()


def activate(db: Session, tenant_id: object) -> None:
    tenant = str(tenant_id)
    _current_tenant.set(tenant)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": tenant},
        )


def deactivate() -> None:
    _current_tenant.set(None)


@event.listens_for(Session, "after_begin")
def _apply_tenant_to_transaction(
    session: Session, transaction, connection
) -> None:  # noqa: ANN001 - assinatura do SQLAlchemy
    tenant = _current_tenant.get()
    if tenant and connection.dialect.name == "postgresql":
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": tenant},
        )
