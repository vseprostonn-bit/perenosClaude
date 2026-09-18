"""Сохранённые разборы: запись после разбора и чтение для «Мои разборы».

Зачем. Раньше разбор жил в памяти процесса бота (FSM) и во вкладке мини-аппа.
Вернуться к нему было нельзя: пользовательница разбирала фото заново, тратила
лимит, а мы - запрос к vision, и ссылки во второй раз могли быть другими. А
после рестарта бота кнопки под старым разбором отвечали «Больше похожих нет»,
хотя вещи были.

Теперь разбор пишется в таблицу `scans` один раз, и бот, и мини-апп читают его
оттуда. Карточки - снимком (см. `Scan`), поэтому разбор открывается тем же,
даже если фид успел обновиться.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item, Scan
from app.services.lookscan import LookItem

if TYPE_CHECKING:
    from app.services.catalog import Match

# Кандидатов на вещь: первый идёт карточкой, остальные - в «Похожие».
# Порядок и скоринг задаёт матчинг, здесь только глубина показа.
MAX_PRODUCTS = 8
RECENT_LIMIT = 20
MSK = timezone(timedelta(hours=3))


def product_snapshot(item: Item) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "price": item.price,
        "old_price": item.old_price,
        "store": item.source,
        "photo_url": item.photo_url,
        "buy_url": item.buy_url,
    }


def slot_entry(look: LookItem, confident: list[Match], log_id: int | None = None) -> dict[str, Any]:
    """Слот разбора: что увидели на фото и что нашли в каталоге."""
    best = confident[0] if confident else None
    return {
        "slot": look.category,
        "name": look.name,
        "color": look.color,
        "search_query": look.search_query,
        "match_percent": best.percent if best else 0,
        "confidence": best.confidence if best else "none",
        "log_id": log_id,
        "products": [product_snapshot(m.item) for m in confident[:MAX_PRODUCTS]],
    }


def look_of(entry: dict[str, Any]) -> LookItem:
    """Вещь с фото обратно из слота - для кнопок поиска на маркетплейсах."""
    name = entry.get("name") or ""
    return LookItem(
        category=entry.get("slot") or "",
        name=name,
        color=entry.get("color") or "",
        search_query=entry.get("search_query") or name,
    )


async def save_scan(
    session: AsyncSession,
    user_id: int,
    source: str,
    vibe: str,
    gender: str | None,
    entries: list[dict[str, Any]],
    tg_file_id: str | None = None,
) -> Scan:
    scan = Scan(
        user_id=user_id,
        source=source,
        vibe=(vibe or "")[:255],
        gender=gender,
        tg_file_id=tg_file_id,
        items=entries,
    )
    session.add(scan)
    await session.commit()
    return scan


async def get_scan(session: AsyncSession, user_id: int, scan_id: int) -> Scan | None:
    """Разбор по id - только свой. Чужой для вызывающего кода не существует."""
    scan = await session.get(Scan, scan_id)
    if scan is None or scan.user_id != user_id:
        return None
    return scan


async def recent_scans(
    session: AsyncSession, user_id: int, limit: int = RECENT_LIMIT
) -> list[Scan]:
    query = (
        select(Scan)
        .where(Scan.user_id == user_id)
        .order_by(Scan.created_at.desc(), Scan.id.desc())
        .limit(limit)
    )
    return list((await session.scalars(query)).all())


def local_time(scan: Scan) -> datetime:
    """Время разбора по Москве. SQLite отдаёт время без зоны - это UTC."""
    ts = scan.created_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(MSK)


def date_label(scan: Scan) -> str:
    return local_time(scan).strftime("%d.%m, %H:%M")


def vibe_title(scan: Scan) -> str:
    """Короткое имя разбора: вайб до пояснения, иначе нейтрально."""
    head = (scan.vibe or "").split(" - ")[0].strip().rstrip(".")
    return head[:1].upper() + head[1:] if head else "Разбор образа"


def found_count(scan: Scan) -> int:
    return sum(1 for entry in scan.items or [] if entry.get("products"))


def summary(scan: Scan) -> dict[str, Any]:
    """Строка списка «Мои разборы»."""
    firsts = [e["products"][0] for e in scan.items or [] if e.get("products")]
    return {
        "id": scan.id,
        "created_at": local_time(scan).isoformat(),
        "date_label": date_label(scan),
        "title": vibe_title(scan),
        "items": len(scan.items or []),
        "found": len(firsts),
        "cover_url": next((p.get("photo_url") for p in firsts if p.get("photo_url")), None),
        "total": sum(int(p.get("price") or 0) for p in firsts),
    }


def payload(scan: Scan) -> dict[str, Any]:
    """Разбор целиком в контракте мини-аппа - тот же, что отдаёт POST /api/scan."""
    return {
        "id": scan.id,
        "created_at": local_time(scan).isoformat(),
        "date_label": date_label(scan),
        "vibe": scan.vibe,
        "gender": scan.gender,
        "items": [
            {k: v for k, v in entry.items() if k != "log_id"} for entry in scan.items or []
        ],
    }
