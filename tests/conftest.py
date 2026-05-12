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
    from fastapi.testclient import TestClient

    from app.main import app
    from app.seed import seed

    seed()
    return TestClient(app)
