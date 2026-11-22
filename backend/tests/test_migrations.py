from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import get_settings
from app.db.base import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_alembic_migrations_match_models(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'migrations.db'}"
    settings = get_settings().model_copy(update={"database_url": url})
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option(
        "script_location", str(BACKEND_DIR / "app" / "db" / "migrations")
    )
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")

    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        migrated = {
            table: {
                column["name"]: bool(column["nullable"])
                for column in inspector.get_columns(table)
            }
            for table in inspector.get_table_names()
            if table != "alembic_version"
        }
    finally:
        engine.dispose()

    expected = {
        table.name: {column.name: bool(column.nullable) for column in table.columns}
        for table in Base.metadata.sorted_tables
    }
    assert migrated == expected
