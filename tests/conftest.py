from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def _temporary_database():
    tmp_dir = tempfile.mkdtemp(prefix="hotel-test-")
    db_path = Path(tmp_dir) / "hotel-test.db"
    os.environ["HOTEL_DB_URL"] = f"sqlite:///{db_path}"
    os.environ["SEED_ONLY_IF_EMPTY"] = "0"
    yield
    try:
        db_path.unlink(missing_ok=True)
    except Exception:
        pass


@pytest.fixture()
def client():
    """TestClient autenticado como administrador.

    Esta fixture es la usada por casi todos los tests existentes; añade el
    header ``Authorization: Bearer ...`` automáticamente para no romper los
    flujos legacy ahora que todas las rutas requieren login.
    """
    from fastapi.testclient import TestClient

    from app.main import app
    from app.seed import seed

    seed()
    client = TestClient(app)

    resp = client.post("/api/auth/login", json={"pin": "1234"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture()
def anon_client():
    """TestClient sin token, útil para probar el flujo de login y 401."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.seed import seed

    seed()
    return TestClient(app)
