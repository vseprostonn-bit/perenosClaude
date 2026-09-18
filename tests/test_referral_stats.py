from sqlalchemy.ext.asyncio import AsyncSession

from app.services.payments import create_payment, process_successful_payment
from app.services.referral_stats import blogger_by_tg_username, blogger_stats
from app.services.users import get_or_create_user
from tests.conftest import make_blogger


async def test_blogger_found_case_insensitive(session: AsyncSession) -> None:
    blogger = await make_blogger(session)
    blogger.tg_username = "Vika_NN"
    await session.commit()

    assert await blogger_by_tg_username(session, "vika_nn") is not None
    assert await blogger_by_tg_username(session, "VIKA_NN") is not None
    assert await blogger_by_tg_username(session, "nobody") is None
    assert await blogger_by_tg_username(session, None) is None


async def test_stats_counts_regs_payments_accruals(session: AsyncSession) -> None:
    blogger = await make_blogger(session)
    u1, _ = await get_or_create_user(session, 801, "a", "A", "ref_vika")
    await get_or_create_user(session, 802, "b", "B", "ref_vika")
    await get_or_create_user(session, 803, "c", "C")  # без рефки - не в счёт

    payment, _ = await create_payment(session, u1)
    await process_successful_payment(session, payment.inv_id, f"{payment.amount}.00")

    stats = await blogger_stats(session, blogger)
    assert stats.regs == 2
    assert stats.paid_count == 1
    assert stats.paid_sum == payment.amount
    assert stats.accrued_total == payment.amount * 15 // 100
    assert stats.accrued_pending == stats.accrued_total


async def test_stats_empty_for_new_blogger(session: AsyncSession) -> None:
    blogger = await make_blogger(session, promo_code="fresh")
    stats = await blogger_stats(session, blogger)
    assert stats.regs == 0 and stats.paid_count == 0 and stats.accrued_total == 0
