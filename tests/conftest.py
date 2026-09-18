from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base, Blogger, Item, Outfit, OutfitItem, Subscription


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # StaticPool: одна in-memory база на все сессии теста
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s


async def make_blogger(
    session: AsyncSession, promo_code: str = "vika", rev_months: int = 6
) -> Blogger:
    blogger = Blogger(name="Вика", promo_code=promo_code, rev_months=rev_months)
    session.add(blogger)
    await session.commit()
    return blogger


async def make_outfit(
    session: AsyncSession,
    slug: str,
    style: str = "casual",
    budget_tier: str = "mid",
    status: str = "published",
) -> Outfit:
    item = Item(
        source="lamoda",
        external_id=f"ext-{slug}",
        title=f"Вещь {slug}",
        category="top",
        price=2990,
        product_url=f"https://example.com/{slug}",
    )
    session.add(item)
    await session.flush()
    outfit = Outfit(
        slug=slug, title=f"Образ {slug}", style=style, budget_tier=budget_tier, status=status
    )
    session.add(outfit)
    await session.flush()
    session.add(OutfitItem(outfit_id=outfit.id, item_id=item.id, slot="top"))
    await session.commit()
    return outfit


async def make_subscription(session: AsyncSession, user_id: int, days: int = 30) -> Subscription:
    sub = Subscription(
        user_id=user_id,
        price=299,
        expires_at=datetime.now(UTC) + timedelta(days=days),
    )
    session.add(sub)
    await session.commit()
    return sub
