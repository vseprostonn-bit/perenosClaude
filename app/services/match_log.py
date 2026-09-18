"""Запись показанных карточек и обратной связи по ним.

Зачем: без этих данных нельзя ни понять, где ошибается матчинг, ни обучить
ранжирование. Логируем не только итоговый скор, но и разложение по сигналам -
иначе потом невозможно сказать, какой именно сигнал соврал.

Методология - docs/metodologiya-matchinga-2026-09-03.md, раздел 5.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MatchLog
from app.services.catalog import Match
from app.services.lookscan import LookItem

log = logging.getLogger(__name__)


async def record_shown(
    session: AsyncSession, user_id: int | None, look: LookItem, match: Match, position: int
) -> int | None:
    """Пишет показанную карточку. Возвращает id записи - он уходит в кнопку «Не то».

    Падение лога не должно рушить ответ пользовательнице, поэтому ошибки
    гасим и продолжаем без обратной связи по этой карточке.
    """
    try:
        row = MatchLog(
            user_id=user_id,
            slot=look.category,
            query=(look.search_query or look.name)[:255],
            item_id=match.item.id,
            position=position,
            score=match.score,
            confidence=match.confidence,
            signals=match.signals,
        )
        session.add(row)
        await session.flush()
        return int(row.id)
    except Exception as exc:  # noqa: BLE001 - лог не важнее ответа
        log.warning("не записал показ карточки: %s", exc)
        return None


async def record_feedback(session: AsyncSession, log_id: int, feedback: str) -> MatchLog | None:
    """Отмечает реакцию: buy, similar или not_it."""
    row = await session.get(MatchLog, log_id)
    if row is None:
        return None
    row.feedback = feedback
    await session.flush()
    return row


async def rejection_rate(session: AsyncSession, slot: str | None = None) -> float:
    """Доля карточек, помеченных «не то». Метрика здоровья матчинга на живых людях."""
    query = select(MatchLog)
    if slot:
        query = query.where(MatchLog.slot == slot)
    rows = (await session.scalars(query)).all()
    if not rows:
        return 0.0
    rejected = sum(1 for r in rows if r.feedback == "not_it")
    return round(rejected / len(rows), 3)
