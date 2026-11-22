"""Ativa RLS por tenant no PostgreSQL (opt-in).

Antes de rodar:
- use um role de aplicação dono das tabelas;
- crie/garanta um role separado para o worker com ``BYPASSRLS``;
- defina RLS_ENABLED=true na API.

Uso:
    python -m scripts.enable_rls --apply

O script é idempotente: recria as policies e ativa FORCE RLS nas tabelas de
domínio. Sem ``--apply`` apenas mostra o que faria.
"""

import argparse

from sqlalchemy import text

from app.db.session import get_engine

TABLES = (
    "ig_accounts",
    "login_attempts",
    "jobs",
    "media_assets",
    "insights_snapshots",
    "webhook_endpoints",
    "webhook_deliveries",
    "audit_logs",
)

POLICY = """
CREATE POLICY tenant_isolation ON {table}
USING (tenant_id::text = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true))
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Ativa RLS por tenant no PostgreSQL")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="aplica as policies (sem a flag apenas lista as tabelas)",
    )
    args = parser.parse_args()

    engine = get_engine()
    if engine.dialect.name != "postgresql":
        print("RLS exige PostgreSQL; dialect atual:", engine.dialect.name)
        return 1
    if not args.apply:
        print("Tabelas que receberiam RLS:", ", ".join(TABLES))
        print("Rode com --apply para aplicar.")
        return 0

    with engine.begin() as connection:
        for table in TABLES:
            connection.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            connection.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
            connection.execute(
                text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
            )
            connection.execute(text(POLICY.format(table=table)))
    print("RLS ativado. Garanta que o role do worker tenha BYPASSRLS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
