import os
from collections.abc import Iterator

from cryptography.fernet import Fernet

# Ambiente precisa estar pronto antes de importar app.*
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "JWT_SECRET": "test-secret-" + "x" * 40,
        "SECRETS_KEYS": Fernet.generate_key().decode(),
        "REGISTRATION_ENABLED": "true",
        "DATABASE_URL": "sqlite+pysqlite://",
        # Limites altos por padrão; os testes de rate limit usam um guard próprio.
        "AUTH_LOGIN_LIMIT": "1000",
        "AUTH_REGISTER_LIMIT": "1000",
        "AUTH_REFRESH_LIMIT": "1000",
        "AUTH_MAX_FAILED_LOGINS": "1000",
    }
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_media_storage
from app.core.config import get_settings
from app.core.crypto import get_cipher
from app.core.ratelimit import reset_auth_guard
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services.device import get_device_provider
from app.services.ig_gateway import get_ig_gateway
from app.services.storage import LocalMediaStorage
from app.workers.worker import JobWorker
from tests.fakes import FakeIgGateway


class FakeDeviceProvider:
    def generate(self) -> dict:
        return {
            "device_settings": {"manufacturer": "X", "model": "FakePhone"},
            "uuids": {
                "phone_id": "11111111-1111-1111-1111-111111111111",
                "uuid": "22222222-2222-2222-2222-222222222222",
            },
            "user_agent": "Instagram 269.0.0.18.75 Android",
            "locale": "en_US",
        }


@pytest.fixture
def engine(tmp_path) -> Iterator[Engine]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def ig_gateway() -> FakeIgGateway:
    return FakeIgGateway()


@pytest.fixture
def media_storage(tmp_path) -> LocalMediaStorage:
    return LocalMediaStorage(tmp_path / "media")


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    ig_gateway: FakeIgGateway,
    media_storage: LocalMediaStorage,
) -> Iterator[TestClient]:
    def override_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    reset_auth_guard()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_device_provider] = lambda: FakeDeviceProvider()
    app.dependency_overrides[get_ig_gateway] = lambda: ig_gateway
    app.dependency_overrides[get_media_storage] = lambda: media_storage
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def worker(
    session_factory: sessionmaker[Session],
    ig_gateway: FakeIgGateway,
    media_storage: LocalMediaStorage,
) -> JobWorker:
    return JobWorker(
        session_factory=session_factory,
        cipher=get_cipher(),
        gateway=ig_gateway,
        storage=media_storage,
        settings=get_settings(),
        worker_id="test-worker",
    )
