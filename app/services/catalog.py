"""Поиск реальных вещей в каталоге под разобранную с фото вещь.

Два разных этапа вместо одного:

  1) ОТБОР - широко и быстро. Жёсткие фильтры (категория, пол, наличие) плюс
     три источника кандидатов: цвет с соседними оттенками, слова типа вещи в
     названии, ближайшие по фото из индекса эмбеддингов. Раньше здесь была
     случайная выборка: при 18 700 женских позиций шанс поймать нужную вещь
     был около 4%.

  2) РЕРАНК - узко и точно. Взвешенная сумма сигналов: визуальная близость,
     совпадение паспорта вещи, цвет, слова названия, вменяемость цены. Веса
     нормируются по тем сигналам, которые реально доступны, поэтому отсутствие
     индекса эмбеддингов не ломает ранжирование, а лишь ослабляет его.

Отдельно важное: если лучший кандидат набрал мало, лучше честно вернуть пусто,
чем показать «похожее» наугад. Пользовательница прощает «не нашла», но не
прощает уверенно показанную не ту вещь.

Методология и пороги - docs/metodologiya-matchinga-2026-09-03.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item
from app.services import attributes, embeddings
from app.services.feed_import import _norm_color
from app.services.lookscan import LookItem

# слова, не несущие смысла для матчинга (пол, предлоги)
_STOP = {
    "женская", "женские", "женский", "женское", "мужская", "мужской", "мужские",
    "и", "с", "из", "для", "на", "в", "по", "the", "a",
}

# Веса сигналов. Визуальный - главный, когда он есть: фото не врёт про фасон.
# Паспорт защищает от «цвет совпал, а крой другой». Цена лишь отсекает выбросы.
WEIGHTS: dict[str, float] = {
    "visual": 0.45,
    "attrs": 0.25,
    "color": 0.15,
    "words": 0.10,
    "price": 0.05,
}

# Пороги уверенности. Подбираются на контрольном наборе: scripts/eval_matching.py
EXACT_MIN = 0.80   # показываем как «это она»
CLOSE_MIN = 0.55   # «очень похоже», с честным процентом
WEAK_MIN = 0.25    # ниже - молчим и предлагаем поиск на маркетплейсах

# Сколько кандидатов тянем из каждого источника до реранка
POOL_PER_SOURCE = 300
VISUAL_CANDIDATES = 150


@dataclass
class Match:
    """Кандидат с разложением скора - его же пишем в лог для обучения."""

    item: Item
    score: float
    signals: dict[str, float] = field(default_factory=dict)

    @property
    def confidence(self) -> str:
        if self.score >= EXACT_MIN:
            return "exact"
        if self.score >= CLOSE_MIN:
            return "close"
        return "weak"

    @property
    def percent(self) -> int:
        """Честный процент похожести для показа пользовательнице."""
        return int(round(self.score * 100))


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[а-яёa-z0-9]+", text.lower())
    return {w for w in words if len(w) >= 3 and w not in _STOP}


def product_key(item: Item) -> tuple[str, str, str]:
    """Один товар для пользовательницы: магазин, фото карточки, название.

    Фиды заводят отдельную позицию на каждый размер - одинаковые название,
    цена и фото, id подряд. Без схлопывания восемь кандидатов бывали одними
    кроссовками в восьми размерах, а «Похожие» показывали одно и то же. Фото
    одно на все размеры, но у разных цветов разное - цвета не склеиваются.
    Название в ключе страхует от общей заглушки «нет фото» у разных вещей.
    """
    photo = (item.photo_url or "").split("?", 1)[0]
    title = " ".join((item.title or "").lower().split())
    return item.source or "", photo, title


def _type_keywords(passport: attributes.Attributes) -> tuple[str, ...]:
    """Слова, по которым ищем тип вещи в названии карточки."""
    if not passport.type:
        return ()
    return attributes.TYPES.get(passport.type, ())


def _price_score(price: int, pool_median: float | None) -> float | None:
    """Отсекает выбросы: вещь в разы дороже типичной по этой категории.

    Само по себе несовпадение цены - не грех, поэтому вес у сигнала маленький,
    а вменяемая цена получает единицу.
    """
    if not pool_median or pool_median <= 0:
        return None
    ratio = price / pool_median
    if ratio > 3.5 or ratio < 0.2:
        return 0.0
    if ratio > 2.0 or ratio < 0.4:
        return 0.5
    return 1.0


def _combine(signals: dict[str, float | None]) -> tuple[float, dict[str, float]]:
    """Взвешенная сумма по доступным сигналам.

    None означает «сигнала нет», а не «ноль»: отсутствие индекса эмбеддингов или
    неопределённый цвет не должны штрафовать кандидата. Веса нормируются по тому,
    что реально известно.
    """
    known = {k: v for k, v in signals.items() if v is not None}
    if not known:
        return 0.0, {}
    total_weight = sum(WEIGHTS[k] for k in known)
    if total_weight <= 0:
        return 0.0, {}
    score = sum(WEIGHTS[k] * v for k, v in known.items()) / total_weight
    return round(score, 4), {k: round(v, 4) for k, v in known.items()}


async def _collect_candidates(
    session: AsyncSession,
    look: LookItem,
    passport: attributes.Attributes,
    want_color: str | None,
    gender: str | None,
    visual_ids: list[int],
) -> list[Item]:
    """Пул кандидатов из трёх источников плюс страховка."""
    base = select(Item).where(Item.category == look.category, Item.in_stock.is_(True))
    if gender:
        base = base.where(Item.gender.in_((gender, "unisex")))

    pool: dict[int, Item] = {}

    # 1. Цвет и соседние оттенки: бежевый и песочный на фото различаются светом.
    if want_color:
        colors = [want_color, *attributes.COLOR_NEIGHBOURS.get(want_color, ())]
        query = base.where(Item.color.in_(colors)).limit(POOL_PER_SOURCE)
        for item in (await session.scalars(query)).all():
            pool[item.id] = item

    # 2. Тип вещи в названии карточки - «тренч» отсекает пальто и куртки.
    keywords = _type_keywords(passport)
    if keywords:
        query = base.where(or_(*[Item.title.ilike(f"%{k}%") for k in keywords]))
        for item in (await session.scalars(query.limit(POOL_PER_SOURCE))).all():
            pool.setdefault(item.id, item)

    # 3. Ближайшие по фото - единственный источник, который найдёт вещь,
    #    название которой не совпало ни одним словом.
    if visual_ids:
        query = base.where(Item.id.in_(visual_ids))
        for item in (await session.scalars(query)).all():
            pool.setdefault(item.id, item)

    # 4. Страховка: пул пуст, но в категории что-то есть - берём выборку,
    #    чтобы предложить хоть что-то вместо молчания.
    if not pool:
        for item in (await session.scalars(base.order_by(func.random()).limit(120))).all():
            pool.setdefault(item.id, item)

    # Вето по типу: категория в каталоге приходит из фида и местами врёт, из-за
    # чего под слот «верх» попадала обувь и пользовательница видела ботинки с
    # подписью «поло». Тип из названия надёжнее категории продавца.
    # Заодно отсекаем карточки без рабочей ссылки: кнопка «Купить», которая
    # никуда не ведёт, хуже отсутствия карточки.
    kept = []
    for item in pool.values():
        if attributes.slots_conflict(look.category, attributes.parse_title(item.title)):
            continue
        if not str(item.buy_url or "").startswith("http"):
            continue
        kept.append(item)
    return kept


async def search_scored(
    session: AsyncSession,
    look: LookItem,
    gender: str | None = None,
    limit: int = 3,
    photo_vector: Any = None,
) -> list[Match]:
    """Кандидаты со скорами, отсортированные по убыванию.

    photo_vector - вектор вырезанной с фото вещи. Пока кроп не реализован,
    сюда можно передавать вектор всего кадра: сигнал слабее, но не вреден,
    потому что вес нормируется вместе с остальными.
    """
    passport = look.passport()
    want_color = _norm_color(look.color) or _norm_color(look.search_query)
    query_tokens = _tokens(f"{look.name} {look.search_query}")

    visual_ids: list[int] = []
    if photo_vector is not None:
        visual_ids = embeddings.nearest(photo_vector, VISUAL_CANDIDATES)
    pool = await _collect_candidates(session, look, passport, want_color, gender, visual_ids)
    if not pool:
        return []

    visual_scores: dict[int, float] = {}
    if photo_vector is not None:
        visual_scores = embeddings.similarity(photo_vector, [i.id for i in pool])
    pool_median = median([i.price for i in pool]) if pool else None

    matches: list[Match] = []
    for item in pool:
        item_passport = attributes.parse_title(item.title)
        attrs = attributes.attribute_score(passport, item_passport)
        words = query_tokens & _tokens(item.title)
        signals: dict[str, float | None] = {
            "visual": visual_scores.get(item.id),
            "attrs": attrs if (passport.known() and item_passport.known()) else None,
            "color": attributes.color_score(want_color, item.color) if want_color else None,
            "words": min(1.0, len(words) / 2) if query_tokens else None,
            "price": _price_score(item.price, pool_median),
        }
        score, used = _combine(signals)
        matches.append(Match(item=item, score=score, signals=used))

    # При равном скоре - меньший id: выдача не прыгает от порядка строк в пуле.
    matches.sort(key=lambda m: (-m.score, m.item.id))
    unique: list[Match] = []
    seen: set[tuple[str, str, str]] = set()
    for match in matches:
        key = product_key(match.item)
        if key in seen:
            continue  # тот же товар другого размера - уже показан лучший
        seen.add(key)
        unique.append(match)
        if len(unique) >= limit:
            break
    return unique


async def search_catalog(
    session: AsyncSession,
    look: LookItem,
    gender: str | None = None,
    limit: int = 3,
    photo_vector: Any = None,
) -> list[Item]:
    """Совместимая обёртка: только вещи, только те, в которых мы уверены.

    Слабые кандидаты не возвращаются намеренно - пусть бот честно скажет, что
    точного совпадения нет, и предложит поиск на маркетплейсах.
    """
    matches = await search_scored(session, look, gender, limit, photo_vector)
    return [m.item for m in matches if m.score >= WEAK_MIN]
