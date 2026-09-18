"""Единый список маркетплейсов: код, название, шаблон поиска.

Используется и в клавиатуре разбора, и в настройке «где искать».
Порядок = порядок кнопок. Код хранится в User.search_marketplaces (csv).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Marketplace:
    code: str
    name: str
    search_url: str  # {q} - urlencoded запрос


# Lamoda убрана 10.09.2026: партнёрка отказала, вещей оттуда в каталоге нет,
# и кнопка выглядела обещанием, которого мы не выполняем.
MARKETPLACES: list[Marketplace] = [
    Marketplace("wb", "WB", "https://www.wildberries.ru/catalog/0/search.aspx?search={q}"),
    Marketplace("ozon", "Ozon", "https://www.ozon.ru/search/?text={q}"),
    Marketplace("ym", "Я.Маркет", "https://market.yandex.ru/search?text={q}"),
    Marketplace("mm", "МегаМаркет", "https://megamarket.ru/catalog/?q={q}"),
]

BY_CODE: dict[str, Marketplace] = {m.code: m for m in MARKETPLACES}
DEFAULT_CODES: str = ",".join(m.code for m in MARKETPLACES)  # по умолчанию все включены


def parse_codes(raw: str | None) -> list[str]:
    """csv из профиля -> валидные коды в порядке MARKETPLACES. Пусто/битое -> все."""
    if not raw:
        return [m.code for m in MARKETPLACES]
    chosen = {c for c in raw.split(",") if c in BY_CODE}
    if not chosen:  # все выключить нельзя - иначе кнопок покупки нет
        return [m.code for m in MARKETPLACES]
    return [m.code for m in MARKETPLACES if m.code in chosen]


def enabled_marketplaces(raw: str | None) -> list[Marketplace]:
    return [BY_CODE[c] for c in parse_codes(raw)]
