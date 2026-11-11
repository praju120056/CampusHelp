"""Database engine and session. SQLite for the demo; the schema stays Postgres-compatible."""
from sqlalchemy import create_engine, event, inspect, text
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
    _add_missing_columns()


def _add_missing_columns() -> None:
    """create_all never alters an existing table, so add columns introduced after a database was made.
    Works on SQLite and Postgres; no data is touched."""
    inspector = inspect(engine)
    if "timetable_slots" in inspector.get_table_names():
        have = {c["name"] for c in inspector.get_columns("timetable_slots")}
        if "batch" not in have:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE timetable_slots ADD COLUMN batch VARCHAR(10)"))


def drop_all():
    import app.models  # noqa: F401

    Base.metadata.drop_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
