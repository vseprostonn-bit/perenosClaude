"""Подбор образов по анкете и учёт фри-лимита."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Outfit, Subscription, User, UserOutfitView


async def has_active_subscription(session: AsyncSession, user_id: int) -> bool:
    now = datetime.now(UTC)
    sub_id = await session.scalar(
        select(Subscription.id)
        .where(Subscription.user_id == user_id, Subscription.expires_at > now)
        .limit(1)
    )
    return sub_id is not None


async def viewed_count(session: AsyncSession, user_id: int) -> int:
    count = await session.scalar(
        select(func.count()).select_from(UserOutfitView).where(UserOutfitView.user_id == user_id)
    )
    return int(count or 0)


async def can_view_new_outfit(session: AsyncSession, user_id: int, free_limit: int) -> bool:
    if await has_active_subscription(session, user_id):
        return True
    return await viewed_count(session, user_id) < free_limit


async def register_view(session: AsyncSession, user_id: int, outfit_id: int) -> None:
    """Идемпотентно: повторный просмотр того же образа лимит не съедает."""
    exists = await session.get(UserOutfitView, (user_id, outfit_id))
    if exists is None:
        session.add(UserOutfitView(user_id=user_id, outfit_id=outfit_id))
        await session.commit()


async def next_outfits_for(session: AsyncSession, user: User, limit: int = 3) -> list[Outfit]:
    """Подборка непросмотренных опубликованных образов под анкету.

    Порядок добора: точное совпадение стиль+бюджет -> совпадение стиля -> любой.
    Фолбэк нужен, чтобы бот не молчал при бедном каталоге (фаза 0).
    """
    seen = select(UserOutfitView.outfit_id).where(UserOutfitView.user_id == user.id)
    picked: list[Outfit] = []
    picked_ids: set[int] = set()

    async def pick(*conditions: object, ignore_seen: bool = False) -> None:
        if len(picked) >= limit:
            return
        where = [Outfit.status == "published", *conditions]
        if not ignore_seen:
            where.append(Outfit.id.not_in(seen))
        query = select(Outfit).where(*where).order_by(Outfit.id).limit(limit)  # type: ignore[arg-type]
        for outfit in (await session.scalars(query)).all():
            if outfit.id not in picked_ids and len(picked) < limit:
                picked.append(outfit)
                picked_ids.add(outfit.id)

    if user.style and user.budget:
        await pick(Outfit.style == user.style, Outfit.budget_tier == user.budget)
    if user.style:
        await pick(Outfit.style == user.style)
    await pick()
    # превью не должно молчать: если всё уже просмотрено - показываем любые
    if not picked:
        await pick(ignore_seen=True)
    return picked


async def next_outfit_for(session: AsyncSession, user: User) -> Outfit | None:
    """Первый образ из подборки (используется в тестах и как шорткат)."""
    outfits = await next_outfits_for(session, user, limit=1)
    return outfits[0] if outfits else None
