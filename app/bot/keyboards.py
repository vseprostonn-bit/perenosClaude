from pathlib import Path
from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app import texts
from app.config import get_settings
from app.marketplaces import MARKETPLACES, enabled_marketplaces, parse_codes
from app.models import Outfit
from app.services.lookscan import LookItem


def sizes_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=s, callback_data=f"size:{s}") for s in texts.SIZES[:3]],
        [InlineKeyboardButton(text=s, callback_data=f"size:{s}") for s in texts.SIZES[3:]],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def styles_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"style:{code}")]
        for code, label in texts.STYLES.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def budgets_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"budget:{code}")]
        for code, label in texts.BUDGETS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def show_outfits_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_SHOW_OUTFITS, callback_data="outfit:more")]
        ]
    )


def selection_kb(outfits: list[Outfit]) -> InlineKeyboardMarkup:
    pick_row = [
        InlineKeyboardButton(text=texts.btn_outfit(n), callback_data=f"outfit:pick:{outfit.id}")
        for n, outfit in enumerate(outfits, start=1)
    ]
    more_row = [InlineKeyboardButton(text=texts.BTN_MORE_VARIANTS, callback_data="outfit:more")]
    return InlineKeyboardMarkup(inline_keyboard=[pick_row, more_row])


def outfit_kb(outfit: Outfit) -> InlineKeyboardMarkup:
    rows = []
    for oi in outfit.items:
        slot = texts.SLOT_NAMES.get(oi.slot, oi.slot)
        source = texts.SOURCE_NAMES.get(oi.item.source, oi.item.source)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Купить: {slot} ({source})",
                    url=oi.item.buy_url,
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=texts.BTN_MORE_VARIANTS, callback_data="outfit:more")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def paywall_kb(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.BTN_SUBSCRIBE, url=url)]]
    )


_APP_JS = Path(__file__).resolve().parents[2] / "web" / "miniapp" / "app.js"


def _miniapp_version() -> int:
    """Кеш-бастер из mtime app.js: меняется при каждой правке фронта.

    Telegram агрессивно кеширует мини-апп по URL и «Очистить кеш» не всегда чистит
    WebView. Разный ?v= = разный адрес = свежая загрузка, без ручного бампа версии.
    """
    try:
        return int(_APP_JS.stat().st_mtime)
    except OSError:
        return 1


def miniapp_url() -> str:
    """Адрес мини-аппа с кеш-бастером. Пусто - кнопки не будет: Telegram не примет не-https."""
    settings = get_settings()
    url = settings.miniapp_url or f"{settings.public_base_url.rstrip('/')}/app"
    if not url.startswith("https://"):
        return ""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}v={_miniapp_version()}"


def main_menu_kb() -> InlineKeyboardMarkup:
    """Пять пунктов, без эмодзи и без настроек: меню - это вход в продукт.

    Настройка площадок переехала под результат разбора, где она и нужна:
    в главном меню она читалась как обязательный шаг перед началом.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *([[InlineKeyboardButton(text=texts.BTN_OPEN_APP,
                                      web_app=WebAppInfo(url=miniapp_url()))]]
              if miniapp_url() else []),
            [InlineKeyboardButton(text=texts.BTN_SCAN_PHOTO, callback_data="menu:scan")],
            [InlineKeyboardButton(text=texts.BTN_MY_SCANS, callback_data="scans:list")],
            [InlineKeyboardButton(text=texts.BTN_OUTFITS_MENU, callback_data="menu:outfits")],
            [InlineKeyboardButton(text=texts.BTN_INVITE, callback_data="menu:invite")],
        ]
    )


def where_search_kb(raw_codes: str | None) -> InlineKeyboardMarkup:
    """Галочки площадок: тап переключает, состояние в тексте кнопки."""
    chosen = set(parse_codes(raw_codes))
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✅' if m.code in chosen else '⬜️'} {m.name}",
                callback_data=f"where:toggle:{m.code}",
            )
        ]
        for m in MARKETPLACES
    ]
    rows.append([InlineKeyboardButton(text=texts.BTN_WHERE_DONE, callback_data="menu:scan")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _search_buttons(query: str, label: str, raw_codes: str | None) -> list[InlineKeyboardButton]:
    markets = enabled_marketplaces(raw_codes)
    return [
        InlineKeyboardButton(
            text=f"{label}: {m.name}" if i == 0 else m.name,
            url=m.search_url.format(q=query),
        )
        for i, m in enumerate(markets)
    ]


def _chunk(buttons: list[InlineKeyboardButton], size: int = 3) -> list[list[InlineKeyboardButton]]:
    return [buttons[i : i + size] for i in range(0, len(buttons), size)]


def lookscan_kb(
    items: list[LookItem],
    raw_codes: str | None = None,
    scan_id: int | None = None,
    indices: list[int] | None = None,
) -> InlineKeyboardMarkup:
    """Вещи без карточки: поиск по выбранным площадкам + «искать только эту».

    «Только эту» ссылается на слот сохранённого разбора (`only:<scan>:<слот>`),
    поэтому работает и после рестарта бота. Без разбора кнопки нет - ей не на
    что сослаться. indices - номера слотов в разборе, если вещи идут не подряд.
    """
    rows: list[list[InlineKeyboardButton]] = []
    for n, item in enumerate(items):
        query = quote(item.search_query)
        label = texts.CATEGORY_NAMES.get(item.category, item.category)
        rows.extend(_chunk(_search_buttons(query, label, raw_codes)))
        if scan_id is not None:
            idx = indices[n] if indices is not None else n
            rows.append([InlineKeyboardButton(
                text=texts.btn_only_item(label), callback_data=f"only:{scan_id}:{idx}"
            )])
    rows.append([InlineKeyboardButton(text=texts.BTN_SCAN_MORE, callback_data="menu:scan")])
    rows.append([InlineKeyboardButton(text=texts.BTN_OUTFITS_MENU, callback_data="menu:outfits")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def catalog_card_kb(
    buy_url: str,
    source: str,
    more_ref: tuple[int, int, int] | None = None,
    log_id: int | None = None,
) -> InlineKeyboardMarkup:
    """Карточка реальной вещи: «Купить», «Ещё похожие» и «Не то».

    «Не то» - самый ценный сигнал в продукте: он и чинит выдачу прямо сейчас,
    и копится как разметка для обучения ранжирования.

    more_ref - (разбор, слот, с какой вещи показывать): кнопка читает
    сохранённый разбор из базы, а не память процесса.
    """
    store = texts.SOURCE_NAMES.get(source, source)
    rows = [[InlineKeyboardButton(text=f"Купить в {store}", url=buy_url)]]
    second: list[InlineKeyboardButton] = []
    if more_ref is not None:
        scan_id, idx, start = more_ref
        second.append(InlineKeyboardButton(
            text=texts.BTN_MORE_SIMILAR, callback_data=f"more:{scan_id}:{idx}:{start}"
        ))
    if log_id is not None:
        second.append(InlineKeyboardButton(text="Не то", callback_data=f"notit:{log_id}"))
    if second:
        rows.append(second)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_scans_kb(buttons: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """Список сохранённых разборов: по кнопке на разбор, свежие сверху."""
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"scans:open:{scan_id}")]
        for scan_id, label in buttons
    ]
    rows.append([InlineKeyboardButton(text=texts.BTN_SCAN_MORE, callback_data="menu:scan")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def scan_footer_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_SCAN_MORE, callback_data="menu:scan")],
            [InlineKeyboardButton(text=texts.BTN_OUTFITS_MENU, callback_data="menu:outfits")],
        ]
    )


def only_item_kb(item: LookItem, raw_codes: str | None = None) -> InlineKeyboardMarkup:
    """Одна вещь крупно: только её кнопки поиска + вернуться к образу."""
    query = quote(item.search_query)
    label = texts.CATEGORY_NAMES.get(item.category, item.category)
    rows = _chunk(_search_buttons(query, label, raw_codes))
    rows.append([InlineKeyboardButton(text=texts.BTN_SCAN_MORE, callback_data="menu:scan")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
