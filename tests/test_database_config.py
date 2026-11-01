import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from app.core.config import Settings
from app.database import create_database_engine, normalize_database_url
from app.main import app
import app.main as main_module


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "postgres://localhost/openbench",
            "postgresql+psycopg://localhost/openbench",
        ),
        (
            "postgresql://localhost/openbench",
            "postgresql+psycopg://localhost/openbench",
        ),
        (
            "postgresql+psycopg2://localhost/openbench",
            "postgresql+psycopg://localhost/openbench",
        ),
        ("sqlite:///./openbench.db", "sqlite:///./openbench.db"),
    ],
)
def test_database_url_normalization(source, expected):
    assert normalize_database_url(source) == expected


def test_sqlite_engine_enables_foreign_key_enforcement():
    engine = create_database_engine("sqlite://")
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("PRAGMA foreign_keys")) == 1
    finally:
        engine.dispose()


def test_secret_key_must_not_be_short():
    with pytest.raises(ValidationError):
        Settings(SECRET_KEY="too-short")


def test_health_endpoint_is_liveness_only():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_readiness_returns_200_when_database_is_available(monkeypatch):
    class ReadyConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _statement):
            return None

    class ReadyEngine:
        def connect(self):
            return ReadyConnection()

    class ReadyInspector:
        def get_table_names(self):
            return main_module.REQUIRED_TABLES

    monkeypatch.setattr(main_module, "engine", ReadyEngine())
    monkeypatch.setattr(main_module, "inspect", lambda _connection: ReadyInspector())
    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "status": "ready",
        "database": "connected",
    }


def test_readiness_failure_uses_redacted_503_response(monkeypatch):
    class FailedEngine:
        def connect(self):
            raise RuntimeError("private database connection detail")

    monkeypatch.setattr("app.main.engine", FailedEngine())
    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "success": False,
        "status": "not_ready",
        "database": "disconnected",
    }
    assert "private database connection detail" not in response.text
