"""Статистика блогерки: регистрации, оплаты, начисления."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Blogger, Payment, ReferralAccrual, User


@dataclass
class BloggerStats:
    regs: int
    paid_count: int
    paid_sum: int
    accrued_total: int
    accrued_pending: int


async def blogger_by_tg_username(session: AsyncSession, username: str | None) -> Blogger | None:
    if not username:
        return None
    return await session.scalar(
        select(Blogger).where(func.lower(Blogger.tg_username) == username.lower())
    )


async def blogger_stats(session: AsyncSession, blogger: Blogger) -> BloggerStats:
    referred = select(User.id).where(User.referrer_blogger_id == blogger.id)

    regs = await session.scalar(
        select(func.count()).select_from(User).where(User.referrer_blogger_id == blogger.id)
    )
    paid_count = await session.scalar(
        select(func.count())
        .select_from(Payment)
        .where(Payment.status == "paid", Payment.user_id.in_(referred))
    )
    paid_sum = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == "paid", Payment.user_id.in_(referred)
        )
    )
    accrued_total = await session.scalar(
        select(func.coalesce(func.sum(ReferralAccrual.amount), 0)).where(
            ReferralAccrual.blogger_id == blogger.id
        )
    )
    accrued_pending = await session.scalar(
        select(func.coalesce(func.sum(ReferralAccrual.amount), 0)).where(
            ReferralAccrual.blogger_id == blogger.id, ReferralAccrual.status == "pending"
        )
    )
    return BloggerStats(
        regs=int(regs or 0),
        paid_count=int(paid_count or 0),
        paid_sum=int(paid_sum or 0),
        accrued_total=int(accrued_total or 0),
        accrued_pending=int(accrued_pending or 0),
    )
