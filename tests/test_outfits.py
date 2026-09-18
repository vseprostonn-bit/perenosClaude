from sqlalchemy.ext.asyncio import AsyncSession

from app.services.outfits import (
    can_view_new_outfit,
    next_outfit_for,
    next_outfits_for,
    register_view,
    viewed_count,
)
from app.services.users import get_or_create_user
from tests.conftest import make_outfit, make_subscription

FREE_LIMIT = 3


async def test_pick_prefers_exact_match(session: AsyncSession) -> None:
    await make_outfit(session, "casual-mid", style="casual", budget_tier="mid")
    await make_outfit(session, "office-high", style="office", budget_tier="high")
    user, _ = await get_or_create_user(session, 1, "u", "U")
    user.style, user.budget = "office", "high"
    await session.commit()

    outfit = await next_outfit_for(session, user)
    assert outfit is not None and outfit.slug == "office-high"


async def test_pick_falls_back_to_any(session: AsyncSession) -> None:
    await make_outfit(session, "casual-low", style="casual", budget_tier="low")
    user, _ = await get_or_create_user(session, 2, "u", "U")
    user.style, user.budget = "sport", "high"
    await session.commit()

    outfit = await next_outfit_for(session, user)
    assert outfit is not None and outfit.slug == "casual-low"


async def test_selection_exact_first_no_duplicates(session: AsyncSession) -> None:
    await make_outfit(session, "office-high", style="office", budget_tier="high")
    await make_outfit(session, "office-low", style="office", budget_tier="low")
    await make_outfit(session, "casual-mid", style="casual", budget_tier="mid")
    await make_outfit(session, "draft", style="office", budget_tier="high", status="draft")
    user, _ = await get_or_create_user(session, 10, "u", "U")
    user.style, user.budget = "office", "high"
    await session.commit()

    outfits = await next_outfits_for(session, user, limit=3)
    slugs = [o.slug for o in outfits]
    assert slugs[0] == "office-high"  # точное совпадение первым
    assert set(slugs) == {"office-high", "office-low", "casual-mid"}  # добор без дублей
    assert len(slugs) == len(set(slugs))


async def test_selection_skips_seen(session: AsyncSession) -> None:
    first = await make_outfit(session, "s-one")
    await make_outfit(session, "s-two")
    user, _ = await get_or_create_user(session, 11, "u", "U")
    await register_view(session, user.id, first.id)

    outfits = await next_outfits_for(session, user, limit=3)
    assert [o.slug for o in outfits] == ["s-two"]


async def test_drafts_never_shown(session: AsyncSession) -> None:
    await make_outfit(session, "draft-1", status="draft")
    user, _ = await get_or_create_user(session, 3, "u", "U")
    assert await next_outfit_for(session, user) is None


async def test_seen_outfits_not_repeated(session: AsyncSession) -> None:
    first = await make_outfit(session, "one")
    await make_outfit(session, "two")
    user, _ = await get_or_create_user(session, 4, "u", "U")

    await register_view(session, user.id, first.id)
    outfit = await next_outfit_for(session, user)
    assert outfit is not None and outfit.slug == "two"


async def test_free_limit_counts_unique_views(session: AsyncSession) -> None:
    outfits = [await make_outfit(session, f"o{i}") for i in range(FREE_LIMIT)]
    user, _ = await get_or_create_user(session, 5, "u", "U")

    for outfit in outfits:
        assert await can_view_new_outfit(session, user.id, FREE_LIMIT)
        await register_view(session, user.id, outfit.id)

    # повторный просмотр того же образа лимит не съедает
    await register_view(session, user.id, outfits[0].id)
    assert await viewed_count(session, user.id) == FREE_LIMIT
    # новый образ сверх лимита - нельзя
    assert not await can_view_new_outfit(session, user.id, FREE_LIMIT)


async def test_subscription_lifts_limit(session: AsyncSession) -> None:
    outfits = [await make_outfit(session, f"s{i}") for i in range(FREE_LIMIT)]
    user, _ = await get_or_create_user(session, 6, "u", "U")
    for outfit in outfits:
        await register_view(session, user.id, outfit.id)

    assert not await can_view_new_outfit(session, user.id, FREE_LIMIT)
    await make_subscription(session, user.id)
    assert await can_view_new_outfit(session, user.id, FREE_LIMIT)


async def test_expired_subscription_does_not_lift(session: AsyncSession) -> None:
    outfit = await make_outfit(session, "e0")
    user, _ = await get_or_create_user(session, 7, "u", "U")
    await register_view(session, user.id, outfit.id)
    await make_subscription(session, user.id, days=-1)
    assert not await can_view_new_outfit(session, user.id, free_limit=1)
