"""Тексты бота. Все строки в одном месте - легко править без кода."""

from app.models import Outfit

WELCOME = (
    "Привет! Я Образ - подбираю готовые луки с вещами с Wildberries, Ozon, "
    "Lamoda и Яндекс Маркета.\n\n"
    "Больше не надо часами листать поиск: отвечу на пару вопросов и покажу "
    "образы под твой стиль - с ценами и ссылками, где купить каждую вещь.\n\n"
    "А ещё кидай мне фото понравившегося лука (хоть скрин с Pinterest) - "
    "разложу его на вещи и подскажу, где такие искать."
)

ASK_SIZE = "Какой у тебя размер одежды?"
ASK_STYLE = "Какой стиль тебе ближе?"
ASK_BUDGET = "Какой бюджет на образ комфортен?"
SURVEY_DONE = "Готово! Собираю образы под тебя..."
WELCOME_AFTER_SURVEY = "Образы подобраны - жми кнопку!"

NO_OUTFITS = (
    "Пока не нашла образ под твои параметры - каталог пополняется каждый день. "
    "Загляни чуть позже!"
)


def selection_text(outfits: list[Outfit]) -> str:
    lines = ["Подобрала для тебя:", ""]
    for n, outfit in enumerate(outfits, start=1):
        total = sum(oi.item.price for oi in outfit.items)
        lines.append(f"{n}. {outfit.title} - {_rub(total)}")
    lines.append("")
    lines.append("Жми на образ - покажу вещи, цены и где купить.")
    return "\n".join(lines)

PAYWALL_TITLE = "Бесплатные образы закончились"


def paywall_text(price: int) -> str:
    return (
        f"{PAYWALL_TITLE}\n\n"
        f"Подписка открывает все образы без ограничений: {price} руб/мес.\n"
        "Новые луки каждую неделю, подбор под твой размер и бюджет."
    )


SUBSCRIPTION_ACTIVATED = (
    "Оплата прошла - подписка активна 30 дней! Жми «Показать образы» и листай без лимита."
)

STATS_NOT_BLOGGER = (
    "Команда /stats доступна партнёрам программы. Хочешь рекомендовать Образ "
    "и получать процент с подписок? Напиши нам!"
)


def blogger_stats_text(name: str, code: str, regs: int, paid_count: int,
                       paid_sum: int, accrued_pending: int, accrued_total: int) -> str:
    return (
        f"Статистика партнёра {name} (код {code})\n\n"
        f"Пришло по твоей ссылке: {regs} чел\n"
        f"Оплат подписки: {paid_count} на {_rub(paid_sum)}\n"
        f"Начислено тебе всего: {_rub(accrued_total)}\n"
        f"К выплате (ожидает): {_rub(accrued_pending)}\n\n"
        f"Твоя ссылка: https://t.me/obraz_style_bot?start=ref_{code}"
    )

BTN_SHOW_OUTFITS = "Показать образы"
BTN_MORE_VARIANTS = "Ещё варианты"
BTN_SUBSCRIBE = "Оформить подписку"

BTN_OPEN_APP = "Открыть приложение"
BTN_INVITE = "Пригласить подругу"
BTN_SCAN_PHOTO = "Разобрать лук по фото"
BTN_OUTFITS_MENU = "Готовые образы"
BTN_SCAN_MORE = "Разобрать ещё фото"
BTN_MY_SCANS = "Мои разборы"
BTN_MORE_SIMILAR = "Ещё похожие"
BTN_WHERE_SEARCH = "Где ещё искать"
BTN_WHERE_DONE = "Готово"

WHERE_SEARCH_TITLE = (
    "Где искать вещи? Отметь площадки - под каждым разбором покажу кнопки "
    "только по ним. Тапни, чтобы включить или выключить."
)
WHERE_SAVED = "Сохранила! Площадки обновлены."


def btn_only_item(label: str) -> str:
    return f"🔎 Искать только {label.lower()}"


def only_item_caption(name: str, color: str) -> str:
    return f"Ищем только эту вещь:\n{name}, {color}\n\nКнопки ниже - где купить."

SCAN_INVITE = (
    "Кидай фото: скрин с Pinterest, из Instagram, фото витрины или просто "
    "красивый наряд с улицы. Разложу образ на вещи и подскажу, где такие искать."
)

PREMIUM_ACTIVE = "Подписка активна! Разборы по фото и образы - без ограничений."

LOOKSCAN_WAIT = "Разбираю образ... 10-15 секунд"

LOOKSCAN_NOT_OUTFIT = (
    "Хм, не вижу на фото образа. Кинь фото лука - с Pinterest, из соцсетей "
    "или просто скрин красивого наряда - и я разложу его на вещи."
)

LOOKSCAN_FAIL = "Не получилось разобрать фото, попробуй ещё раз чуть позже."


def lookscan_paywall_text(price: int) -> str:
    return (
        "Понравился разбор по фото?\n\n"
        f"С подпиской ({price} руб/мес) кидай сколько хочешь луков в день - "
        "разложу каждый на вещи и покажу, где купить. Плюс все готовые образы "
        "без ограничений."
    )


LOOKSCAN_DAILY_LIMIT = (
    "На сегодня лимит разборов исчерпан - завтра продолжим! "
    "А пока посмотри готовые образы."
)

CATEGORY_NAMES: dict[str, str] = {
    "top": "Верх",
    "bottom": "Низ",
    "dress": "Платье",
    "outerwear": "Верхняя одежда",
    "shoes": "Обувь",
    "bag": "Сумка",
    "accessory": "Аксессуар",
}


def btn_outfit(n: int) -> str:
    return f"Образ {n}"

STYLES: dict[str, str] = {
    "casual": "Кэжуал",
    "office": "Офис",
    "date": "Свидание",
    "sport": "Спорт-шик",
    "basic": "База",
}

BUDGETS: dict[str, str] = {
    "low": "до 5 000 р",
    "mid": "5-10 тыс р",
    "high": "10 тыс р +",
}

SIZES: list[str] = ["XS", "S", "M", "L", "XL", "Другой"]

SLOT_NAMES: dict[str, str] = {
    "top": "Верх",
    "bottom": "Низ",
    "shoes": "Обувь",
    "bag": "Сумка",
    "accessory": "Аксессуар",
}

SOURCE_NAMES: dict[str, str] = {
    "lamoda": "Lamoda",
    "wb": "WB",
    "ozon": "Ozon",
    "ym": "Я.Маркет",
    "befree": "Befree",
    "sela": "SELA",
    "tsum": "ЦУМ",
    "finnflare": "Finn-Flare",
    "loverepublic": "Love Republic",
    "incantoeu": "Incanto",
    "incanto": "Incanto",
}


def match_confidence_line(confidence: str, percent: int) -> str:
    """Честная строка про уверенность.

    Показываем ровно то, что посчитали. Красивый «94% похоже» при реальных
    сорока убивает доверие быстрее, чем отсутствие результата.
    """
    if confidence == "exact":
        return "Это она"
    if confidence == "close":
        return f"Очень похоже, {percent}%"
    return f"Точной не нашла, вот самое близкое - {percent}%"


def catalog_card_caption(
    category: str, title: str, price: int, source: str,
    confidence: str | None = None, percent: int | None = None,
) -> str:
    slot = CATEGORY_NAMES.get(category, category)
    store = SOURCE_NAMES.get(source, source)
    head = f"{slot} · {title}\n{_rub(price)} — {store}"
    if confidence and percent is not None:
        head = f"{match_confidence_line(confidence, percent)}\n{head}"
    return head


LOOKSCAN_FOUND_HINT = "Нашла эти вещи в наличии - жми «Купить». Не то? Скажи, и подберу заново."


LOOKSCAN_MISSING_HINT = "По этим вещам пока нет точных совпадений - вот поиск на маркетплейсах:"
NOT_IT_THANKS = "Поняла, запомнила"
NOT_IT_HINT = (
    "Записала, что не то - в следующий раз подберу точнее. "
    "А пока вот поиск этой вещи на маркетплейсах:"
)

def invited_bonus_line(bonus: int) -> str:
    """Приписка к приветствию для тех, кто пришёл по ссылке подруги."""
    return (
        f"\n\nТы пришла по приглашению, поэтому разборов у тебя больше: "
        f"плюс {bonus} сверх обычных. Карта не нужна."
    )


def invite_text(link: str, invited: int, credits: int, percent: int, friend_scans: int) -> str:
    """Экран приглашения: ссылка, что получают обе стороны, текущий счёт."""
    lines = [
        "Пригласи подругу - следующий месяц дешевле.",
        "",
        f"Она получит {friend_scans} дополнительных разбора бесплатно, ты - скидку "
        f"{percent}% на следующую оплату. Скидка начисляется, когда подруга оплатит "
        "подписку, а не просто зайдёт в бота.",
        "",
        "Твоя ссылка:",
        link,
        "",
    ]
    if invited:
        lines.append(f"Пришло по ссылке: {invited}")
    if credits:
        lines.append(f"Накоплено скидок: {credits} - применится к следующей оплате")
    if not invited and not credits:
        lines.append("Пока никто не пришёл. Ссылку можно кинуть в личку или в сторис.")
    return "\n".join(lines)


SCAN_MORE_PROMPT = "Кинь ещё скрин лука - разберу. Или загляни в готовые образы."


def _rub(price: int) -> str:
    return f"{price:,}".replace(",", " ") + " р"


def lookscan_caption(vibe: str, items: list[tuple[str, str, str]]) -> str:
    """items: (category, name, color)."""
    lines = ["Разобрала твой образ!", ""]
    if vibe:
        lines[0] = f"Разобрала твой образ - {vibe.lower().rstrip('.')}!"
    for category, name, color in items:
        lines.append(f"{CATEGORY_NAMES.get(category, category)}: {name}, {color}")
    lines.append("")
    lines.append("Ниже - что нашла в каталоге. Разбор сохранится в «Мои разборы».")
    return "\n".join(lines)


# ---------------------------------------------------------------- мои разборы

MY_SCANS_TITLE = (
    "Твои разборы, свежие сверху. Открываются с теми же вещами и ссылками "
    "и лимит не тратят."
)
MY_SCANS_EMPTY = "Разборов пока нет. Кинь фото лука - разберу, и он сохранится здесь."
SCAN_OUTDATED = (
    "Этот разбор был до обновления бота. Свежие - в «Мои разборы», "
    "или кинь фото заново."
)
NO_MORE_SIMILAR = "Больше похожих не нашла"
SAVED_SCAN_PRICES_NOTE = "Цены - на момент разбора, в магазине могут отличаться."


def scan_button(date_label: str, title: str, found: int, total: int) -> str:
    """Кнопка разбора в списке: когда, что за образ, сколько нашлось."""
    day = date_label.split(",")[0]
    return f"{day} · {title[:28]} · нашла {found} из {total}"


def saved_scan_caption(
    date_label: str, vibe: str, items: list[tuple[str, str, str]]
) -> str:
    """Подпись к фото сохранённого разбора. items: (category, name, color)."""
    lines = [f"Разбор от {date_label}"]
    if vibe:
        lines.append(vibe.rstrip("."))
    lines.append("")
    for category, name, color in items:
        lines.append(f"{CATEGORY_NAMES.get(category, category)}: {name}, {color}")
    return "\n".join(lines)


def outfit_caption(outfit: Outfit) -> str:
    lines = [outfit.title, ""]
    total = 0
    for oi in outfit.items:
        slot = SLOT_NAMES.get(oi.slot, oi.slot)
        source = SOURCE_NAMES.get(oi.item.source, oi.item.source)
        lines.append(f"{slot}: {oi.item.title} - {_rub(oi.item.price)} ({source})")
        total += oi.item.price
    lines.append("")
    lines.append(f"Весь образ: {_rub(total)}")
    lines.append("Кнопки ниже - купить каждую вещь.")
    return "\n".join(lines)
