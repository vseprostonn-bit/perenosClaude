"""Регистрация пользовательницы и первое касание реф-метки.

Правило атрибуции: первое касание. Реф-метка пишется только при создании
пользователя и никогда не перезаписывается (план, edge case 4).
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Blogger, User
from app.services.pricing import price_bucket

REF_PREFIX = "ref_"
SRC_PREFIX = "src_"
INVITE_PREFIX = "inv_"  # пользовательская рефералка: inv_<tg_id пригласившей>


@dataclass
class StartRef:
    blogger_code: str | None = None
    source: str | None = None
    inviter_id: int | None = None


def parse_start_payload(payload: str | None) -> StartRef:
    if not payload:
        return StartRef()
    payload = payload.strip()
    if payload.startswith(REF_PREFIX):
        code = payload[len(REF_PREFIX) :]
        return StartRef(blogger_code=code or None)
    if payload.startswith(SRC_PREFIX):
        src = payload[len(SRC_PREFIX) :]
        return StartRef(source=src[:64] or None)
    if payload.startswith(INVITE_PREFIX):
        raw = payload[len(INVITE_PREFIX) :]
        return StartRef(inviter_id=int(raw)) if raw.isdigit() else StartRef()
    return StartRef()


async def get_or_create_user(
    session: AsyncSession,
    tg_id: int,
    username: str | None,
    first_name: str | None,
    start_payload: str | None = None,
) -> tuple[User, bool]:
    """Возвращает (user, created). Реф-метка применяется только к новому пользователю."""
    user = await session.get(User, tg_id)
    if user is not None:
        return user, False

    ref = parse_start_payload(start_payload)
    referrer_id: int | None = None
    if ref.blogger_code:
        blogger = await session.scalar(
            select(Blogger).where(Blogger.promo_code == ref.blogger_code)
        )
        if blogger is not None:
            referrer_id = blogger.id

    # Пригласившая должна существовать и не быть той же самой: ссылка на себя -
    # первый и самый простой способ накрутить скидки.
    inviter_id: int | None = None
    if (
        ref.inviter_id
        and ref.inviter_id != tg_id
        and await session.get(User, ref.inviter_id) is not None
    ):
        inviter_id = ref.inviter_id

    user = User(
        id=tg_id,
        username=username,
        first_name=first_name,
        ab_price_bucket=price_bucket(tg_id),
        referrer_blogger_id=referrer_id,
        invited_by_user_id=inviter_id,
        referral_source=ref.source or (ref.blogger_code if referrer_id is None else None),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # Гонка двух одновременных /start: конкурент успел создать юзера первым
        await session.rollback()
        existing = await session.get(User, tg_id)
        if existing is None:
            raise
        return existing, False
    return user, True
