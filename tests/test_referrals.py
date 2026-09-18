from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.users import get_or_create_user, parse_start_payload
from tests.conftest import make_blogger


def test_parse_payload_variants() -> None:
    assert parse_start_payload("ref_vika").blogger_code == "vika"
    assert parse_start_payload("src_kanal1").source == "kanal1"
    assert parse_start_payload(None).blogger_code is None
    assert parse_start_payload("garbage").blogger_code is None
    assert parse_start_payload("ref_").blogger_code is None


async def test_first_touch_saved(session: AsyncSession) -> None:
    blogger = await make_blogger(session)
    user, created = await get_or_create_user(session, 100, "u", "U", "ref_vika")
    assert created
    assert user.referrer_blogger_id == blogger.id


async def test_first_touch_not_overwritten(session: AsyncSession) -> None:
    blogger = await make_blogger(session)
    await make_blogger(session, promo_code="dasha")
    user, _ = await get_or_create_user(session, 100, "u", "U", "ref_vika")
    user, created = await get_or_create_user(session, 100, "u", "U", "ref_dasha")
    assert not created
    assert user.referrer_blogger_id == blogger.id


async def test_unknown_promo_kept_as_source(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, 200, "u", "U", "ref_nobody")
    assert user.referrer_blogger_id is None
    assert user.referral_source == "nobody"


async def test_seed_source_saved(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, 300, "u", "U", "src_kanal1")
    assert user.referral_source == "kanal1"


async def test_price_bucket_assigned(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, 301, "u", "U", None)
    assert user.ab_price_bucket == 301 % 3


async def test_double_start_race_survives(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Два одновременных /start: конкурент вставил юзера между проверкой и вставкой."""
    async with session_factory() as s1, session_factory() as s2:
        real_get = s1.get
        calls = 0

        async def blind_first_get(*args: Any, **kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            if calls == 1:
                return None  # первая проверка "не видит" юзера - как в реальной гонке
            return await real_get(*args, **kwargs)

        s1.get = blind_first_get  # type: ignore[method-assign]

        await get_or_create_user(s2, 500, "second", "B", None)  # конкурент успел первым
        user, created = await get_or_create_user(s1, 500, "first", "A", "ref_x")

        assert not created
        assert user.id == 500
        assert user.username == "second"
