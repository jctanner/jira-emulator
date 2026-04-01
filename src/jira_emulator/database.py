"""Async SQLAlchemy engine and session management for SQLite."""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from jira_emulator.config import get_settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def _set_sqlite_pragmas(dbapi_conn, connection_record):
    """Enable WAL mode and foreign keys for SQLite connections."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_engine(database_url: str | None = None):
    """Create an async SQLAlchemy engine."""
    url = database_url or get_settings().DATABASE_URL
    engine = create_async_engine(url, echo=False)
    event.listen(engine.sync_engine, "connect", _set_sqlite_pragmas)
    return engine


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


async def get_db():
    """FastAPI dependency that yields an async database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db(engine=None):
    """Create all tables from ORM metadata."""
    e = engine or get_engine()
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def reset_engine():
    """Reset the global engine and session factory (used in tests)."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
