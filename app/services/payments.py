"""Оплата подписки: токены пейвола, Robokassa, обработка успешного платежа.

Схема (docs/2026-08-24-oplata-v-tg-i-web.md): бот даёт ссылку на страницу
/pay?t=<токен> на нашем домене, оплата уходит в Robokassa, ResultURL-вебхук
активирует подписку и начисляет долю блогеру.
"""

import hashlib
import hmac
import json
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Blogger, Payment, ReferralAccrual, Subscription, User
from app.services.pricing import price_for

TOKEN_TTL_HOURS = 48
SUBSCRIPTION_DAYS = 30
ROBOKASSA_BASE = "https://auth.robokassa.ru/Merchant/Index.aspx"


def _sign(payload: str) -> str:
    secret = get_settings().secret_key.encode()
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()[:20]


def make_pay_token(user_id: int, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    expires = int((now + timedelta(hours=TOKEN_TTL_HOURS)).timestamp())
    payload = f"{user_id}.{expires}"
    return f"{payload}.{_sign(payload)}"


def parse_pay_token(token: str, now: datetime | None = None) -> int | None:
    """user_id из токена; None - подделка или истёк."""
    now = now or datetime.now(UTC)
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = f"{parts[0]}.{parts[1]}"
    if not hmac.compare_digest(_sign(payload), parts[2]):
        return None
    try:
        user_id, expires = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if now.timestamp() > expires:
        return None
    return user_id


async def has_paid_before(session: AsyncSession, user_id: int) -> bool:
    paid = await session.scalar(
        select(Payment.id).where(Payment.user_id == user_id, Payment.status == "paid").limit(1)
    )
    return paid is not None


@dataclass
class Offer:
    base_price: int
    price: int
    discount_percent: int


async def offer_for(session: AsyncSession, user: User) -> Offer:
    """Цена для пользовательницы: бакет A/B плюс не более одной скидки.

    Скидки не складываются: иначе накопленные приглашения и промокод блогерки
    вместе могут увести платёж в ноль. Берём наибольшую из применимых.
    """
    settings = get_settings()
    base = price_for(user.id)
    first_payment = not await has_paid_before(session, user.id)

    candidates = [0]
    if user.referrer_blogger_id is not None and first_payment:
        candidates.append(settings.referral_discount_percent)
    if (user.referral_credits or 0) > 0:
        candidates.append(settings.invite_discount_percent)

    discount = min(max(candidates), 100)
    price = round(base * (100 - discount) / 100)
    return Offer(base_price=base, price=price, discount_percent=discount)


async def uses_referral_credit(session: AsyncSession, user: User) -> bool:
    """Списывается ли за этот платёж накопленная скидка за приглашение."""
    settings = get_settings()
    if (user.referral_credits or 0) <= 0:
        return False
    offer = await offer_for(session, user)
    return offer.discount_percent == settings.invite_discount_percent


def _receipt(amount: int) -> str:
    """Чек Робочеков: одна позиция - подписка. СНО общая, без НДС (ст. 145 НК)."""
    receipt = {
        "sno": "osn",
        "items": [
            {
                "name": "Подписка на сервис подбора образов «Образ», 30 дней",
                "quantity": 1,
                "sum": amount,
                "payment_method": "full_payment",
                "payment_object": "service",
                "tax": "none",
            }
        ],
    }
    return json.dumps(receipt, ensure_ascii=False, separators=(",", ":"))


def robokassa_payment_url(inv_id: int, amount: int, description: str) -> str:
    s = get_settings()
    out_sum = f"{amount}.00"
    receipt = _receipt(amount)
    receipt_encoded = urllib.parse.quote(receipt, safe="")
    base = (
        f"{s.robokassa_merchant_login}:{out_sum}:{inv_id}:"
        f"{receipt_encoded}:{s.robokassa_password1}"
    )
    signature = hashlib.md5(base.encode()).hexdigest()  # noqa: S324 - формат Robokassa
    params = {
        "MerchantLogin": s.robokassa_merchant_login,
        "OutSum": out_sum,
        "InvId": str(inv_id),
        "Description": description,
        "Receipt": receipt,
        "SignatureValue": signature,
        "Culture": "ru",
    }
    if s.robokassa_test_mode:
        params["IsTest"] = "1"
    return f"{ROBOKASSA_BASE}?{urllib.parse.urlencode(params)}"


def verify_result_signature(out_sum: str, inv_id: str, signature: str) -> bool:
    s = get_settings()
    expected = hashlib.md5(  # noqa: S324 - формат Robokassa
        f"{out_sum}:{inv_id}:{s.robokassa_password2}".encode()
    ).hexdigest()
    return hmac.compare_digest(expected.lower(), signature.lower())


async def create_payment(session: AsyncSession, user: User) -> tuple[Payment, Offer]:
    offer = await offer_for(session, user)
    payment = Payment(
        user_id=user.id, amount=offer.price, status="pending", inv_id=0,
        used_referral_credit=await uses_referral_credit(session, user),
    )
    session.add(payment)
    await session.flush()  # получаем payment.id
    payment.inv_id = payment.id
    await session.commit()
    return payment, offer


async def process_successful_payment(
    session: AsyncSession, inv_id: int, out_sum: str
) -> int | None:
    """Идемпотентно проводит оплату. Возвращает user_id для уведомления, None - дубль."""
    payment = await session.scalar(select(Payment).where(Payment.inv_id == inv_id))
    if payment is None:
        return None
    if payment.status == "paid":
        return None  # повторный вебхук - уже проведён

    now = datetime.now(UTC)
    payment.status = "paid"
    payment.paid_at = now
    payment.raw = {"out_sum": out_sum}
    session.add(
        Subscription(
            user_id=payment.user_id,
            plan="month",
            price=payment.amount,
            paid_at=now,
            expires_at=now + timedelta(days=SUBSCRIPTION_DAYS),
        )
    )

    user = await session.get(User, payment.user_id)

    # Пользовательская рефералка. Кредит начисляется только когда приглашённая
    # РЕАЛЬНО заплатила: по регистрации накрутить мультиаккаунтами слишком легко.
    if user is not None:
        if payment.used_referral_credit and (user.referral_credits or 0) > 0:
            user.referral_credits -= 1
        first_payment = await _is_first_paid_payment(session, user.id, payment.id)
        if first_payment and user.invited_by_user_id:
            inviter = await session.get(User, user.invited_by_user_id)
            cap = get_settings().invite_max_credits
            if inviter is not None and (inviter.referral_credits or 0) < cap:
                inviter.referral_credits = (inviter.referral_credits or 0) + 1

    if user is not None and user.referrer_blogger_id is not None:
        blogger = await session.get(Blogger, user.referrer_blogger_id)
        if blogger is not None and _within_rev_window(user, blogger, now):
            share = payment.amount * blogger.percent // 100
            if share > 0:
                session.add(
                    ReferralAccrual(
                        blogger_id=blogger.id, payment_id=payment.id, amount=share
                    )
                )
    await session.commit()
    return payment.user_id


async def _is_first_paid_payment(session: AsyncSession, user_id: int, payment_id: int) -> bool:
    """Этот платёж - первый оплаченный у пользовательницы."""
    earlier = await session.scalar(
        select(Payment.id)
        .where(Payment.user_id == user_id, Payment.status == "paid", Payment.id != payment_id)
        .limit(1)
    )
    return earlier is None


def _within_rev_window(user: User, blogger: Blogger, now: datetime) -> bool:
    """Блогер получает долю только в первые rev_months жизни приведённой."""
    created = user.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    window_days = blogger.rev_months * 30
    return now <= created + timedelta(days=window_days)
