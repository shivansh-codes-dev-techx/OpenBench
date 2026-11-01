import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.database import Base
from app.main import app
import app.main as main_module


@pytest.fixture
def isolated_engine(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(main_module, "engine", engine)

    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_health_response_remains_backward_compatible(isolated_engine):
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "status": "healthy",
        "database": "connected",
    }


def test_ready_returns_200_when_all_tables_exist(isolated_engine):
    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "status": "ready",
        "database": "ready",
    }


def test_ready_returns_503_when_a_required_table_is_missing(isolated_engine):
    models.ActivityLog.__table__.drop(bind=isolated_engine)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable"}


def test_ready_returns_503_when_database_is_unavailable(monkeypatch):
    class UnavailableEngine:
        def connect(self):
            raise RuntimeError("database path and SQL details must stay private")

    monkeypatch.setattr(main_module, "engine", UnavailableEngine())

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable"}
    assert "database path" not in response.text
    assert "SQL details" not in response.text
