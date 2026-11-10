"""Database engine and session. SQLite for the demo; the schema stays Postgres-compatible."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


engine = None
SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def init_engine(url: str):
    """(Re)bind the engine. Called at startup and by tests."""
    global engine
    kwargs: dict = {}
    is_sqlite = url.startswith("sqlite")
    in_memory = url in ("sqlite://", "sqlite:///:memory:")
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
        if in_memory:
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _on_connect(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            if not in_memory:
                cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    SessionLocal.configure(bind=engine)
    return engine


def create_all():
    import app.models  # noqa: F401  (registers tables)

    Base.metadata.create_all(engine)


def drop_all():
    import app.models  # noqa: F401

    Base.metadata.drop_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
