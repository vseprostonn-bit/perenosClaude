from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Item(Base):
    """Товар с маркетплейса (из фида Lamoda или добавлен руками)."""

    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_items_source_ext"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(16))  # lamoda | wb | ozon | ym
    external_id: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(64))  # top | bottom | shoes | bag | accessory...
    gender: Mapped[str] = mapped_column(String(8), default="women")  # women | men | unisex
    color: Mapped[str | None] = mapped_column(String(32))
    price: Mapped[int] = mapped_column(Integer)  # рубли
    old_price: Mapped[int | None] = mapped_column(Integer)
    sizes: Mapped[list[str] | None] = mapped_column(JSON)
    photo_url: Mapped[str | None] = mapped_column(String(1024))
    product_url: Mapped[str] = mapped_column(String(1024))
    affiliate_url: Mapped[str | None] = mapped_column(String(1024))
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def buy_url(self) -> str:
        return self.affiliate_url or self.product_url


class Outfit(Base):
    """Образ: собранный лук из вещей-слотов."""

    __tablename__ = "outfits"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    style: Mapped[str] = mapped_column(String(32))  # casual | office | date | sport | basic
    budget_tier: Mapped[str] = mapped_column(String(8))  # low | mid | high
    cover_photo: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | published
    author: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    items: Mapped[list["OutfitItem"]] = relationship(
        back_populates="outfit", order_by="OutfitItem.position", lazy="selectin"
    )


class OutfitItem(Base):
    """Слот образа: какая вещь на какой позиции."""

    __tablename__ = "outfit_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    outfit_id: Mapped[int] = mapped_column(ForeignKey("outfits.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"))
    slot: Mapped[str] = mapped_column(String(16))  # top | bottom | shoes | bag | accessory
    position: Mapped[int] = mapped_column(Integer, default=0)

    outfit: Mapped[Outfit] = relationship(back_populates="items")
    item: Mapped[Item] = relationship(lazy="joined")


class Blogger(Base):
    """UGC-блогер: приводит аудиторию, получает 15% с оплат подписки."""

    __tablename__ = "bloggers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    tg_username: Mapped[str | None] = mapped_column(String(64))
    promo_code: Mapped[str] = mapped_column(String(32), unique=True)
    percent: Mapped[int] = mapped_column(Integer, default=15)
    rev_months: Mapped[int] = mapped_column(Integer, default=6)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    """Пользовательница бота. id = telegram id."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    size: Mapped[str | None] = mapped_column(String(16))
    style: Mapped[str | None] = mapped_column(String(32))
    budget: Mapped[str | None] = mapped_column(String(8))  # low | mid | high
    ab_price_bucket: Mapped[int] = mapped_column(Integer, default=0)
    referrer_blogger_id: Mapped[int | None] = mapped_column(ForeignKey("bloggers.id"))
    referral_source: Mapped[str | None] = mapped_column(String(64))  # utm посева
    survey_done: Mapped[bool] = mapped_column(Boolean, default=False)
    search_marketplaces: Mapped[str | None] = mapped_column(String(64))  # csv кодов, None=все
    # Пользовательская рефералка: кто пригласил и сколько скидок накоплено.
    # Отличается от блогерской (referrer_blogger_id): здесь награда только
    # скидкой, деньги наружу не уходят.
    invited_by_user_id: Mapped[int | None] = mapped_column(BigInteger)
    referral_credits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subscription(Base):
    """Оплаченный период доступа."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    plan: Mapped[str] = mapped_column(String(16), default="month")
    price: Mapped[int] = mapped_column(Integer)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Payment(Base):
    """Платёж Robokassa. inv_id - идемпотентность вебхука."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    inv_id: Mapped[int] = mapped_column(Integer, unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | paid | failed
    raw: Mapped[dict[str, str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Платёж прошёл по накопленной реферальной скидке: нужно, чтобы списать
    # кредит ровно один раз и только при успешной оплате.
    used_referral_credit: Mapped[bool] = mapped_column(Boolean, default=False)


class ReferralAccrual(Base):
    """Начисление блогеру 15% с конкретного платежа."""

    __tablename__ = "referral_accruals"

    id: Mapped[int] = mapped_column(primary_key=True)
    blogger_id: Mapped[int] = mapped_column(ForeignKey("bloggers.id", ondelete="CASCADE"))
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), unique=True)
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | paid
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserOutfitView(Base):
    """Уникальные просмотры образов - учёт фри-лимита."""

    __tablename__ = "user_outfit_views"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    outfit_id: Mapped[int] = mapped_column(
        ForeignKey("outfits.id", ondelete="CASCADE"), primary_key=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MatchLog(Base):
    """Что показали пользовательнице по разбору и как она на это отреагировала.

    Это данные для обучения ранжирования: без разложения скора по сигналам
    потом невозможно понять, какой именно сигнал ошибся. Методология -
    docs/metodologiya-matchinga-2026-09-03.md, раздел 5.
    """

    __tablename__ = "match_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    slot: Mapped[str] = mapped_column(String(32))          # top | bottom | shoes...
    query: Mapped[str] = mapped_column(String(255))        # что искали, для чтения глазами
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"))
    position: Mapped[int] = mapped_column(Integer)         # 1 - первая карточка
    score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(8))     # exact | close | weak
    signals: Mapped[dict[str, float] | None] = mapped_column(JSON)
    feedback: Mapped[str | None] = mapped_column(String(16))  # buy | similar | not_it
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Scan(Base):
    """Сохранённый разбор фото: к нему возвращаются с теми же вещами и ссылками.

    Карточки лежат снимком, а не id: фиды обновляются, вещь в каталоге может
    смениться или пропасть, а разбор должен открываться тем же, что видела
    пользовательница. Само фото на сервере не храним (политика, п. 5) - у бота
    остаётся только file_id, фото живёт в Telegram.

    items - список слотов: {slot, name, color, search_query, match_percent,
    confidence, log_id, products: [{id, title, price, old_price, store,
    photo_url, buy_url}]}. Формат - app/services/scans.py.
    """

    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    source: Mapped[str] = mapped_column(String(8))  # bot | miniapp
    vibe: Mapped[str] = mapped_column(String(255), default="")
    gender: Mapped[str | None] = mapped_column(String(8))
    tg_file_id: Mapped[str | None] = mapped_column(String(255))
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Event(Base):
    """Событие воронки: start, survey_done, outfit_view, paywall_view, paywall_click..."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, str] | None] = mapped_column(JSON)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
