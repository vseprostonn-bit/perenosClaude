"""Чтение записи контрольного набора по номеру вещи, а не по имени слота.

Почему отдельный модуль. Раньше разбор («look») и кандидаты («suggestions»)
находились по имени слота. На фото с двумя аксессуарами (очки и кепка) второй
затирал первый: обе вещи в разметке были подписаны «очки», а кандидаты у обеих
были от кепки. Разметка, замер и пересборка кандидатов должны читать запись
одинаково - поэтому правило живёт в одном месте.

Формат:
  items[i]                   - разметка i-й вещи
  look                       - разбор бота; i-я вещь слота S - это i-е вхождение S
  suggestions_by_item[i]     - кандидаты i-й вещи (пишет annotate_golden resuggest)
  suggestions[slot]          - старый формат, один список на имя слота
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def looks_for_items(data: dict[str, Any]) -> list[dict[str, Any] | None]:
    """Разбор бота для каждой вещи: k-я вещь слота - k-е вхождение слота в look."""
    by_slot: dict[str, list[dict[str, Any]]] = {}
    for look in data.get("look") or []:
        by_slot.setdefault(look.get("slot") or look.get("category") or "", []).append(look)
    seen: Counter[str] = Counter()
    out: list[dict[str, Any] | None] = []
    for item in data.get("items") or []:
        slot = item.get("slot", "")
        pool = by_slot.get(slot, [])
        out.append(pool[seen[slot]] if seen[slot] < len(pool) else None)
        seen[slot] += 1
    return out


def duplicate_slot_indices(data: dict[str, Any]) -> set[int]:
    """Номера вещей, чей слот на фото встречается больше одного раза."""
    items = data.get("items") or []
    counts = Counter(item.get("slot", "") for item in items)
    return {idx for idx, item in enumerate(items) if counts[item.get("slot", "")] > 1}


def candidates_for_items(data: dict[str, Any]) -> tuple[list[list[dict[str, Any]]], bool]:
    """Кандидаты каждой вещи и признак «у двойников кандидаты перепутаны».

    Новый формат - список по номеру вещи. Старый - словарь по имени слота: у
    двух аксессуаров там один список на двоих, и он принадлежит второму.
    """
    items = data.get("items") or []
    by_item = data.get("suggestions_by_item")
    if isinstance(by_item, list) and len(by_item) == len(items):
        return [list(c or []) for c in by_item], False
    by_slot = data.get("suggestions") or {}
    lists = [list(by_slot.get(item.get("slot", ""), [])) for item in items]
    return lists, bool(duplicate_slot_indices(data))


def candidate_key(candidate: dict[str, Any]) -> tuple[str, str]:
    """Товар кандидата: фото и название, как в `catalog.product_key`.

    Магазина в ключе нет: в записях до 15.09 его у кандидатов не сохраняли, а
    ключ должен одинаково работать для старых и новых списков.
    """
    photo = (candidate.get("photo_url") or "").split("?", 1)[0]
    title = " ".join((candidate.get("title") or "").lower().split())
    return photo, title
