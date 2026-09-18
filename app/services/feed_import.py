"""Импорт товарных фидов Admitad (YML) в каталог.

Фид YML: <yml_catalog><shop><offers><offer>. У offer есть name, price,
picture, url (готовая партнёрская ссылка), param Цвет/Размер/Пол,
market_category. Отбираем женское и раскладываем по нашим слотам.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element, iterparse

# market_category / name -> наш слот. Порядок важен: обувь и сумки до одежды.
CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("shoes", ("кроссовк", "кед", "ботильон", "ботинк", "сапог", "туфл", "лофер",
               "босоножк", "балетк", "сандал", "слипон", "мокасин", "угг", "обувь", "челси")),
    ("bag", ("сумк", "рюкзак", "клатч", "шоппер", "поясная сумка")),
    ("accessory", ("шарф", "платок", "шапк", "ремень", "пояс", "очки", "перчатк",
                   "носк", "бельё", "белье", "купальник", "украшен", "серьг", "браслет",
                   "часы", "варежк", "берет", "панам", "кепк", "аксессуар", "пончо")),
    ("dress", ("платье", "сарафан", "комбинезон")),
    ("outerwear", ("куртк", "пальто", "пуховик", "парк", "плащ", "тренч", "жакет",
                   "пиджак", "жилет", "ветровк", "шуба", "бомбер", "анорак", "дублёнк",
                   "дубленк", "кардиган")),
    ("bottom", ("брюк", "джинс", "юбк", "шорт", "легинс", "леггинс", "чинос", "капри")),
    ("top", ("футболк", "блуз", "рубашк", "топ", "джемпер", "свитер", "водолазк",
             "лонгслив", "поло", "толстовк", "худи", "майк", "боди", "туник", "кофт",
             "свитшот", "жакет", "болеро")),
]

# цвет -> нормализованное русское слово (для поиска). Ключи - ru и en вхождения.
COLOR_MAP: dict[str, str] = {
    "чёрн": "черный", "черн": "черный", "black": "черный",
    "бел": "белый", "white": "белый",
    "сер": "серый", "grey": "серый", "gray": "серый",
    "беж": "бежевый", "beige": "бежевый",
    "коричнев": "коричневый", "brown": "коричневый",
    "красн": "красный", "red": "красный",
    "розов": "розовый", "pink": "розовый",
    "бордов": "бордовый",
    "син": "синий", "blue": "синий", "navy": "синий",
    "голуб": "голубой",
    "зелён": "зеленый", "зелен": "зеленый", "green": "зеленый",
    "жёлт": "желтый", "желт": "желтый", "yellow": "желтый",
    "оранж": "оранжевый", "orange": "оранжевый",
    "фиолет": "фиолетовый", "purple": "фиолетовый",
    "сирен": "сиреневый",
    "молочн": "молочный", "кремов": "кремовый", "cream": "кремовый",
    "хаки": "хаки", "khaki": "хаки",
    "мятн": "мятный", "бирюз": "бирюзовый",
    "золот": "золотой", "gold": "золотой",
    "серебр": "серебристый", "silver": "серебристый",
    "пудров": "пудровый", "молоко": "молочный",
}


@dataclass
class FeedItem:
    external_id: str
    title: str
    category: str
    gender: str  # women | men | unisex
    color: str | None
    price: int
    old_price: int | None
    sizes: list[str] = field(default_factory=list)
    photo_url: str | None = None
    product_url: str = ""
    affiliate_url: str | None = None
    in_stock: bool = True


def _slot_for(text: str) -> str | None:
    low = text.lower()
    for slot, keys in CATEGORY_RULES:
        if any(k in low for k in keys):
            return slot
    return None


def _norm_color(raw: str | None) -> str | None:
    if not raw:
        return None
    low = raw.lower()
    for key, norm in COLOR_MAP.items():
        if key in low:
            return norm
    return None


# Детские маркеры. Приложение женское/мужское, детское в образы не пускаем:
# «рубашка для мальчиков» у SELA иначе утекает в женскую выдачу. Отдельный пол
# "kids" фильтр каталога (gender, "unisex") отсекает сам, а импорт не перетирает
# его брендовым дефолтом - вещь сохраняется в базе на будущий детский раздел.
_KIDS_MARKERS = ("мальчик", "девочк", "детск", "для детей", "kids", "юниор")


def _gender(raw: str | None, text: str) -> str:
    """Пол по параметру «Пол» или по словам названия/категории."""
    low = (raw or "").lower()
    tl = text.lower()
    if any(m in low or m in tl for m in _KIDS_MARKERS):
        return "kids"
    # Фиды размечают пол и по-русски, и по-английски (Befree: Пол=male/female).
    # ВАЖНО: "female" содержит "male", поэтому женский проверяем ПЕРВЫМ, иначе
    # 1092 мужских товара Befree утекали в женский каталог как unisex->women.
    if "жен" in low or "female" in low:
        return "women"
    if "муж" in low or "male" in low:
        return "men"
    if "унисекс" in low or "unisex" in low:
        return "unisex"
    if "мужск" in tl or " муж " in tl:
        return "men"
    if "женск" in tl or "жен." in tl:
        return "women"
    return "unisex"  # метки нет - пусть виден обоим


def parse_feed(xml_bytes: bytes) -> Iterator[FeedItem]:
    """Стримовый разбор YML: категория, пол, цвет. Терпим к обрыву больших фидов."""
    import io
    from xml.etree.ElementTree import ParseError

    parser = iterparse(io.BytesIO(xml_bytes), events=("end",))
    try:
        for _event, elem in parser:
            if elem.tag != "offer":
                continue
            item = _offer_to_item(elem)
            if item is not None:
                yield item
            elem.clear()
    except ParseError:
        return  # фид оборвался (битый хвост) - отдаём, что успели разобрать


def _offer_to_item(offer: Element) -> FeedItem | None:
    if offer.get("available", "true") == "false":
        return None
    params = {p.get("name"): (p.text or "") for p in offer.findall("param")}

    name = (offer.findtext("name") or offer.findtext("model") or "").strip()
    market_cat = offer.findtext("market_category") or ""
    # берём лист категории (после последнего /): корень «Одежда, обувь и аксессуары»
    # содержит слово «обувь» и ломал бы классификатор для всех товаров
    leaf = market_cat.rsplit("/", 1)[-1]
    slot = _slot_for(leaf + " " + name)
    if slot is None:
        return None
    gender = _gender(params.get("Пол"), market_cat + " " + name)

    price_raw = offer.findtext("price")
    if not price_raw:
        return None
    try:
        price = int(round(float(price_raw)))
    except ValueError:
        return None
    old_raw = offer.findtext("oldprice")
    old_price = int(round(float(old_raw))) if old_raw else None

    pictures = [p.text for p in offer.findall("picture") if p.text]
    url = offer.findtext("url") or ""
    ext_id = offer.get("id") or offer.findtext("barcode") or url
    sizes = [params["Размер"]] if params.get("Размер") else []
    color = _norm_color(params.get("Цвет")) or _norm_color(name)

    return FeedItem(
        external_id=str(ext_id),
        title=name[:255],
        category=slot,
        gender=gender,
        color=color,
        price=price,
        old_price=old_price if old_price and old_price > price else None,
        sizes=sizes,
        photo_url=pictures[0] if pictures else None,
        product_url=url,
        affiliate_url=url,  # url в фиде - уже партнёрский deeplink
        in_stock=True,
    )
