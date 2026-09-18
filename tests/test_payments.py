import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Payment, ReferralAccrual, Subscription
from app.services.outfits import has_active_subscription
from app.services.payments import (
    create_payment,
    make_pay_token,
    offer_for,
    parse_pay_token,
    process_successful_payment,
    robokassa_payment_url,
    verify_result_signature,
)
from app.services.pricing import price_for
from app.services.users import get_or_create_user
from tests.conftest import make_blogger


def test_pay_token_roundtrip() -> None:
    token = make_pay_token(12345)
    assert parse_pay_token(token) == 12345


def test_pay_token_tamper_rejected() -> None:
    token = make_pay_token(12345)
    assert parse_pay_token(token.replace("12345", "99999", 1)) is None
    assert parse_pay_token("garbage") is None
    assert parse_pay_token("") is None


def test_pay_token_expiry() -> None:
    old = datetime.now(UTC) - timedelta(days=30)
    token = make_pay_token(1, now=old)
    assert parse_pay_token(token) is None


def test_result_signature() -> None:
    s = get_settings()
    good = hashlib.md5(f"299.00:7:{s.robokassa_password2}".encode()).hexdigest()
    assert verify_result_signature("299.00", "7", good)
    assert verify_result_signature("299.00", "7", good.upper())
    assert not verify_result_signature("299.00", "7", "deadbeef")
    assert not verify_result_signature("199.00", "7", good)


def test_payment_url_contains_test_flag_and_signature() -> None:
    url = robokassa_payment_url(5, 299, "Подписка")
    assert "IsTest=1" in url
    assert "SignatureValue=" in url
    assert "InvId=5" in url
    assert "OutSum=299.00" in url


async def test_offer_no_referrer_no_discount(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, 700, "u", "U")
    offer = await offer_for(session, user)
    assert offer.discount_percent == 0
    assert offer.price == offer.base_price == price_for(700)


async def test_offer_referred_gets_discount_once(session: AsyncSession) -> None:
    await make_blogger(session)
    user, _ = await get_or_create_user(session, 701, "u", "U", "ref_vika")
    offer = await offer_for(session, user)
    assert offer.discount_percent == 15
    assert offer.price == round(offer.base_price * 0.85)

    # после первой оплаты скидка исчезает
    payment, _ = await create_payment(session, user)
    await process_successful_payment(session, payment.inv_id, f"{payment.amount}.00")
    offer2 = await offer_for(session, user)
    assert offer2.discount_percent == 0


async def test_payment_activates_subscription_and_accrues(session: AsyncSession) -> None:
    blogger = await make_blogger(session)
    user, _ = await get_or_create_user(session, 702, "u", "U", "ref_vika")
    payment, offer = await create_payment(session, user)
    assert payment.inv_id == payment.id
    assert payment.amount == offer.price

    got_user = await process_successful_payment(session, payment.inv_id, f"{payment.amount}.00")
    assert got_user == user.id
    assert await has_active_subscription(session, user.id)

    accrual = await session.scalar(
        select(ReferralAccrual).where(ReferralAccrual.blogger_id == blogger.id)
    )
    assert accrual is not None
    assert accrual.amount == payment.amount * 15 // 100


async def test_payment_webhook_idempotent(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, 703, "u", "U")
    payment, _ = await create_payment(session, user)

    first = await process_successful_payment(session, payment.inv_id, "299.00")
    second = await process_successful_payment(session, payment.inv_id, "299.00")
    assert first == user.id
    assert second is None

    subs = await session.scalar(
        select(func.count()).select_from(Subscription).where(Subscription.user_id == user.id)
    )
    assert subs == 1


async def test_unknown_invoice_ignored(session: AsyncSession) -> None:
    assert await process_successful_payment(session, 99999, "299.00") is None


async def test_no_accrual_outside_rev_window(session: AsyncSession) -> None:
    blogger = await make_blogger(session, rev_months=3)
    user, _ = await get_or_create_user(session, 704, "u", "U", "ref_vika")
    user.created_at = datetime.now(UTC) - timedelta(days=120)  # 4 месяца - окно 3 мес прошло
    await session.commit()

    payment, _ = await create_payment(session, user)
    await process_successful_payment(session, payment.inv_id, f"{payment.amount}.00")

    accruals = await session.scalar(
        select(func.count()).select_from(ReferralAccrual).where(
            ReferralAccrual.blogger_id == blogger.id
        )
    )
    assert accruals == 0


async def test_paid_flag_visible(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, 705, "u", "U")
    payment, _ = await create_payment(session, user)
    pending = await session.scalar(select(Payment).where(Payment.inv_id == payment.inv_id))
    assert pending is not None and pending.status == "pending"
    await process_successful_payment(session, payment.inv_id, "299.00")
    paid = await session.scalar(select(Payment).where(Payment.inv_id == payment.inv_id))
    assert paid is not None and paid.status == "paid"
