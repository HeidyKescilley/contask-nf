"""SQLite em modo WAL com SQLAlchemy 2."""
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import config

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def engine():
    global _engine, _SessionLocal
    if _engine is None:
        cfg = config()
        cfg.dados_dir.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(cfg.db_url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(_engine, "connect")
        def _pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def sessao() -> Iterator[Session]:
    engine()
    assert _SessionLocal is not None
    with _SessionLocal() as s:
        yield s


def nova_sessao() -> Session:
    """Sessão avulsa para threads (workers da fila)."""
    engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def reiniciar_para_testes() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine, _SessionLocal = None, None
