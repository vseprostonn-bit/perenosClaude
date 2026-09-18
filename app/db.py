from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    if _session_factory is None:
        url = get_settings().database_url
        if url.startswith("sqlite"):
            # WAL и timeout - иначе конкурентные записи ловят "database is locked"
            _engine = create_async_engine(url, connect_args={"timeout": 30})
            from sqlalchemy import event

            @event.listens_for(_engine.sync_engine, "connect")
            def _sqlite_wal(dbapi_conn: object, _record: object) -> None:
                cursor = dbapi_conn.cursor()  # type: ignore[attr-defined]
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()
        else:
            _engine = create_async_engine(url, pool_pre_ping=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


# Лёгкие аддитивные патчи схемы для уже существующей БД (Alembic на проде не гоняем).
# Только ADD COLUMN - безопасно и идемпотентно. Крупные изменения -> Alembic.
_COLUMN_PATCHES: list[tuple[str, str, str]] = [
    ("users", "search_marketplaces", "VARCHAR(64)"),
    ("users", "invited_by_user_id", "BIGINT"),
    ("users", "referral_credits", "INTEGER DEFAULT 0"),
    ("payments", "used_referral_credit", "BOOLEAN DEFAULT 0"),
    ("items", "gender", "VARCHAR(8) DEFAULT 'women'"),
]


def _lost_race(exc: Exception) -> bool:
    """Ошибка значит «это уже сделал соседний процесс», а не поломку схемы.

    uvicorn и бот стартуют одновременно, и оба догоняют схему. Оба видят, что
    колонки нет, оба делают ALTER - второй получает «duplicate column» и раньше
    падал на старте целиком. Для прода это 502 на ровном месте.
    """
    message = str(exc).lower()
    return "duplicate column" in message or "already exists" in message


async def ensure_schema(factory: async_sessionmaker[AsyncSession] | None = None) -> None:
    """Догоняет схему на проде без Alembic: новые таблицы и аддитивные колонки."""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    from app.models import Base, MatchLog, Scan

    # Новые таблицы создаются целиком, существующие не трогаются (checkfirst).
    factory = factory or get_session_factory()
    engine = factory.kw["bind"]
    for table in (MatchLog.__table__, Scan.__table__):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all, tables=[table])
        except OperationalError as exc:
            if not _lost_race(exc):
                raise

    for table_name, column, coltype in _COLUMN_PATCHES:
        async with factory() as session:
            rows = await session.execute(text(f"PRAGMA table_info({table_name})"))
            if column in {r[1] for r in rows}:
                continue
            try:
                await session.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column} {coltype}")
                )
                await session.commit()
            except OperationalError as exc:
                if not _lost_race(exc):
                    raise
