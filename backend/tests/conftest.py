import os
import tempfile
from datetime import datetime

# Test settings must be in place before the app is imported. Real env/.env values are overridden.
os.environ.update(
    {
        "DATABASE_URL": "sqlite://",
        "SCHEDULER_ENABLED": "false",
        "BCRYPT_ROUNDS": "4",
        "DEMO_MODE": "false",
        "GEMINI_API_KEY": "",
        "SMTP_HOST": "",
        "DEMO_EMAIL_TO": "",  # a real .env's test-recipient must not redirect emails inside tests
        "JWT_SECRET": "test-secret-not-for-production-0123456789",
        "UPLOAD_DIR": tempfile.mkdtemp(prefix="educrew-uploads-"),
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db as db_module  # noqa: E402
from app.config import get_settings  # noqa: E402

get_settings.cache_clear()
db_module.init_engine("sqlite://")

from app.main import create_app  # noqa: E402
from app.seed import PASSWORD, seed  # noqa: E402
from app.services import clock, ratelimit  # noqa: E402
from app.services.events import broker  # noqa: E402

FIXED_NOW = datetime(2026, 11, 10, 10, 30)  # a Tuesday


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    state = Clock(FIXED_NOW)
    monkeypatch.setattr(clock, "now", lambda: state.now)
    monkeypatch.setattr(clock, "today", lambda: state.now.date())
    return state


@pytest.fixture
def db(frozen_clock):
    db_module.drop_all()
    db_module.create_all()
    session = db_module.SessionLocal()
    seed(session)
    ratelimit.reset_all()
    broker.recent.clear()
    yield session
    session.close()


@pytest.fixture
def client(db):
    with TestClient(create_app(auto_seed=False)) as c:
        yield c


def auth(client: TestClient, email: str) -> dict:
    res = client.post("/auth/login", json={"email": f"{email}@educrew.local", "password": PASSWORD})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}
