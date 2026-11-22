import uuid

from app.db.rls import activate, current_tenant, deactivate


def test_rls_context_is_noop_on_sqlite(session_factory):
    tenant_id = uuid.uuid4()
    with session_factory() as db:
        activate(db, tenant_id)
        assert current_tenant() == str(tenant_id)
        deactivate()
        assert current_tenant() is None
