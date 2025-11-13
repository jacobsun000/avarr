"""Database helpers built on SQLModel."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .settings import get_settings


settings = get_settings()


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


def init_db() -> None:
    """Create all tables if they do not yet exist."""

    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a SQLModel session with automatic close/rollback handling."""

    session = Session(engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def session_dependency() -> Iterator[Session]:
    """FastAPI dependency wrapper used inside request handlers."""

    with get_session() as session:
        yield session


__all__ = ["engine", "get_session", "init_db", "session_dependency"]
