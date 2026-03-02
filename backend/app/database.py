from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


def _create_engine(database_url: str):
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def get_engine(database_url: str | None = None):
    url = database_url or settings.database_url
    return _create_engine(url)


def get_session_factory(engine=None):
    if engine is None:
        engine = get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


_default_engine = None
_default_session_factory = None


def _get_defaults():
    global _default_engine, _default_session_factory
    if _default_engine is None:
        Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
        _default_engine = get_engine()
        _default_session_factory = get_session_factory(_default_engine)
    return _default_engine, _default_session_factory


def get_db() -> Generator[Session, None, None]:
    _, session_factory = _get_defaults()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
