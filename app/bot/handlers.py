"""Хендлеры бота: /start -> анкета -> визуальная подборка -> раскрытие образа -> пейвол.

Поток: превью-подборки (фото-альбом или список) бесплатны и не тратят лимит;
лимит списывается при раскрытии образа (состав + кнопки покупки).
Хендлеры тонкие: вся логика в app/services/, здесь только диалог.
"""

import asyncio
from contextlib import suppress
from pathlib import Path as FsPath

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto, Message
from aiogram.types import User as TgUser
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import texts
from app.bot import keyboards as kb
from app.config import get_settings
from app.marketplaces import BY_CODE, parse_codes
from app.models import Outfit, Scan, User, UserOutfitView
from app.routes.pay import pay_url_for
from app.services import embeddings, garment_crop, scans
from app.services.catalog import WEAK_MIN, search_scored
from app.services.events import track
from app.services.lookscan import (
    SCAN_EVENT,
    LookItem,
    analyze_look,
    can_scan,
    catalog_gender,
    item_visible,
)
from app.services.match_log import record_feedback, record_shown
from app.services.outfits import (
    can_view_new_outfit,
    has_active_subscription,
    next_outfits_for,
    register_view,
)
from app.services.pricing import price_for
from app.services.referral_stats import blogger_by_tg_username, blogger_stats
from app.services.users import get_or_create_user

router = Router()

PROJECT_ROOT = FsPath(__file__).resolve().parent.parent.parent


def _photo_input(cover: str) -> str | FSInputFile:
    if cover.startswith("http://") or cover.startswith("https://"):
        return cover
    return FSInputFile(PROJECT_ROOT / cover)


class Survey(StatesGroup):
    size = State()
    style = State()
    budget = State()


async def _user_from_event(session: AsyncSession, tg_user: TgUser, payload: str | None) -> User:
    user, created = await get_or_create_user(
        session, tg_user.id, tg_user.username, tg_user.first_name, payload
    )
    if created:
        await track(
            session,
            user.id,
            "start",
            {"ref": payload or "", "bucket": str(user.ab_price_bucket)},
        )
    return user


# «Ещё похожие» присылает варианты порциями: семь карточек подряд - это спам.
SIMILAR_PAGE = 5
# В боте список короче, чем в мини-аппе: это кнопки под сообщением.
BOT_SCANS_LIMIT = 10


def parse_scan_ref(data: str) -> tuple[int, int, int] | None:
    """`more:<разбор>:<слот>[:<с какой>]` и `only:<разбор>:<слот>` -> числа.

    None - старый формат кнопки (`more:<слот>`), который ссылался на память
    процесса. Такие кнопки остались в чатах с разборов до обновления.
    """
    parts = data.split(":")[1:]
    if len(parts) not in (2, 3) or not all(part.isdigit() for part in parts):
        return None
    start = int(parts[2]) if len(parts) == 3 else 1
    return int(parts[0]), int(parts[1]), start


async def _answer_card(
    message: Message, caption: str, photo_url: str | None, markup: object
) -> None:
    """Карточка с фото, а если фото не ушло (битая ссылка магазина) - текстом."""
    try:
        await message.answer_photo(photo_url or "", caption=caption, reply_markup=markup)  # type: ignore[arg-type]
    except Exception:
        await message.answer(caption, reply_markup=markup)  # type: ignore[arg-type]


async def _send_scan(message: Message, scan: Scan, raw_codes: str | None) -> None:
    """Карточки разбора. Один код и сразу после разбора, и из «Мои разборы»."""
    found = False
    missing: list[tuple[int, LookItem]] = []
    for idx, entry in enumerate(scan.items or []):
        products = entry.get("products") or []
        if not products:
            missing.append((idx, scans.look_of(entry)))
            continue
        found = True
        best = products[0]
        cap = texts.catalog_card_caption(
            entry.get("slot") or "", best["title"], best["price"], best["store"],
            confidence=entry.get("confidence"), percent=entry.get("match_percent"),
        )
        markup = kb.catalog_card_kb(
            best["buy_url"], best["store"],
            more_ref=(scan.id, idx, 1) if len(products) > 1 else None,
            log_id=entry.get("log_id"),
        )
        await _answer_card(message, cap, best.get("photo_url"), markup)

    if found:
        await message.answer(texts.LOOKSCAN_FOUND_HINT)
    if missing:
        await message.answer(
            texts.LOOKSCAN_MISSING_HINT,
            reply_markup=kb.lookscan_kb(
                [look for _, look in missing], raw_codes,
                scan_id=scan.id, indices=[idx for idx, _ in missing],
            ),
        )


async def _saved_entry(
    call: CallbackQuery, session: AsyncSession
) -> tuple[Scan, int, int, dict] | None:
    """Слот сохранённого разбора по кнопке. None - кнопка старая или разбор чужой."""
    if call.from_user is None or call.data is None:
        return None
    ref = parse_scan_ref(call.data)
    if ref is None:
        return None
    scan_id, idx, start = ref
    scan = await scans.get_scan(session, call.from_user.id, scan_id)
    if scan is None or idx >= len(scan.items or []):
        return None
    return scan, idx, start, scan.items[idx]


async def _send_selection(message: Message, session: AsyncSession, user: User) -> None:
    """Превью-подборка: фото-альбом (если у всех образов есть обложки) + кнопки выбора."""
    outfits = await next_outfits_for(session, user, limit=3)
    if not outfits:
        await message.answer(texts.NO_OUTFITS)
        return

    await track(session, user.id, "selection_view", {"outfits": ",".join(o.slug for o in outfits)})
    if all(o.cover_photo for o in outfits):
        media = [
            InputMediaPhoto(
                media=_photo_input(outfit.cover_photo or ""),
                caption=texts.btn_outfit(n) + f". {outfit.title}",
            )
            for n, outfit in enumerate(outfits, start=1)
        ]
        # альбом не ушёл (битое фото) - текстовая подборка ниже всё покажет
        with suppress(Exception):
            await message.answer_media_group(media)  # type: ignore[arg-type]
    await message.answer(texts.selection_text(outfits), reply_markup=kb.selection_kb(outfits))


async def _outfits_entry(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    """Вход в готовые образы: анкета, если не пройдена, иначе подборка."""
    if user.survey_done:
        await _send_selection(message, session, user)
        return
    await state.set_state(Survey.size)
    await message.answer(texts.ASK_SIZE, reply_markup=kb.sizes_kb())


@router.message(CommandStart())
async def cmd_start(
    message: Message, command: CommandObject, state: FSMContext, session: AsyncSession
) -> None:
    if message.from_user is None:
        return
    user = await _user_from_event(session, message.from_user, command.args)
    await state.clear()
    greeting = texts.WELCOME
    if user.invited_by_user_id is not None:
        # пришла по приглашению - сразу говорим про бонус, иначе он невидим
        greeting += texts.invited_bonus_line(get_settings().invite_friend_bonus_scans)
    await message.answer(greeting, reply_markup=kb.main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(texts.WELCOME, reply_markup=kb.main_menu_kb())


@router.message(Command("scan"))
async def cmd_scan(message: Message) -> None:
    await message.answer(texts.SCAN_INVITE)


@router.callback_query(F.data == "menu:scan")
async def menu_scan(call: CallbackQuery) -> None:
    if isinstance(call.message, Message):
        await call.message.answer(texts.SCAN_INVITE)
    await call.answer()


@router.message(Command("outfits"))
async def cmd_outfits(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await _user_from_event(session, message.from_user, None)
    await _outfits_entry(message, state, session, user)


@router.callback_query(F.data == "menu:outfits")
async def menu_outfits(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if call.from_user is None or not isinstance(call.message, Message):
        await call.answer()
        return
    user, _ = await get_or_create_user(
        session, call.from_user.id, call.from_user.username, call.from_user.first_name
    )
    await _outfits_entry(call.message, state, session, user)
    await call.answer()


@router.message(Command("premium"))
async def cmd_premium(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await _user_from_event(session, message.from_user, None)
    if await has_active_subscription(session, user.id):
        await message.answer(texts.PREMIUM_ACTIVE)
        return
    price = price_for(user.id)
    await track(session, user.id, "paywall_view", {"price": str(price), "src": "menu"})
    await message.answer(
        texts.paywall_text(price), reply_markup=kb.paywall_kb(pay_url_for(user.id))
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    """Статистика для блогерки: ищем партнёра по её tg-нику."""
    if message.from_user is None:
        return
    blogger = await blogger_by_tg_username(session, message.from_user.username)
    if blogger is None:
        await message.answer(texts.STATS_NOT_BLOGGER)
        return
    stats = await blogger_stats(session, blogger)
    await message.answer(
        texts.blogger_stats_text(
            blogger.name,
            blogger.promo_code,
            stats.regs,
            stats.paid_count,
            stats.paid_sum,
            stats.accrued_pending,
            stats.accrued_total,
        )
    )


@router.message(F.photo)
async def scan_look(message: Message, session: AsyncSession) -> None:
    """«Скрин в образ»: фото лука -> ИИ-разбор на вещи + кнопки поиска."""
    if message.from_user is None or message.bot is None or not message.photo:
        return
    user = await _user_from_event(session, message.from_user, None)

    subscribed = await has_active_subscription(session, user.id)
    if not await can_scan(session, user.id, subscribed):
        if subscribed:
            await message.answer(texts.LOOKSCAN_DAILY_LIMIT, reply_markup=kb.show_outfits_kb())
            return
        price = price_for(user.id)
        await track(session, user.id, "paywall_view", {"price": str(price), "src": "lookscan"})
        await message.answer(
            texts.lookscan_paywall_text(price), reply_markup=kb.paywall_kb(pay_url_for(user.id))
        )
        return

    await message.answer(texts.LOOKSCAN_WAIT)
    photo_buf = await message.bot.download(message.photo[-1])
    if photo_buf is None:
        await message.answer(texts.LOOKSCAN_FAIL)
        return
    photo_bytes = photo_buf.read()
    analysis = await analyze_look(photo_bytes)

    if analysis is None:
        await message.answer(texts.LOOKSCAN_FAIL)
        return
    # Невидимую или выдуманную вещь не показываем. Для сумок, обуви и
    # аксессуаров планка выше - их модель придумывает чаще всего. В подписи
    # тоже только видимые, иначе там вещь, у которой нет ни карточки, ни поиска.
    visible = [look for look in analysis.items if item_visible(look)]
    if not analysis.is_outfit or not visible:
        await message.answer(texts.LOOKSCAN_NOT_OUTFIT)
        return

    # событие = списание лимита; неудачные попытки лимит не тратят
    await track(
        session, user.id, SCAN_EVENT, {"items": str(len(visible)), "vibe": analysis.vibe}
    )

    summary = texts.lookscan_caption(
        analysis.vibe, [(i.category, i.name, i.color) for i in visible]
    )
    await message.answer(summary)

    # Визуальный сигнал считаем по ВЫРЕЗАННОЙ вещи, а не по всему кадру: близость
    # целого фото говорит о фоне и позе, а не о вещи (методология, причина №1).
    # Кроп + энкодер - CPU, уводим в поток. Нет энкодера/индекса -> visual_on False,
    # матчинг честно работает по тексту.
    visual_on = await asyncio.to_thread(embeddings.available)
    # Пол каталога: unisex не схлопываем в женский, иначе мужской лук получал
    # женские вещи. Подробности - catalog_gender.
    gender = catalog_gender(analysis.gender, user.style)
    entries: list[dict] = []
    for look in visible:
        item_vector = None
        if visual_on:
            crop = garment_crop.crop_for(photo_bytes, look.category)
            if crop is not None:
                item_vector = await asyncio.to_thread(embeddings.encode_image, crop)
        # Глубже трёх: первый кандидат идёт карточкой, остальные - в «Ещё похожие».
        scored = await search_scored(
            session, look, gender=gender, limit=scans.MAX_PRODUCTS, photo_vector=item_vector
        )
        # Слабых кандидатов не показываем: честное «не нашла» лучше уверенно
        # показанной не той вещи.
        confident = [m for m in scored if m.score >= WEAK_MIN]
        log_id = None
        if confident:
            log_id = await record_shown(session, user.id, look, confident[0], position=1)
        entries.append(scans.slot_entry(look, confident, log_id))

    # Разбор пишется в базу до отправки карточек: кнопки под ними ссылаются
    # на него и поэтому переживают рестарт бота. Фото не храним - только
    # file_id, само фото остаётся в Telegram.
    scan = await scans.save_scan(
        session, user.id, "bot", analysis.vibe, gender, entries,
        tg_file_id=message.photo[-1].file_id,
    )
    await _send_scan(message, scan, user.search_marketplaces)
    await message.answer(texts.SCAN_MORE_PROMPT, reply_markup=kb.scan_footer_kb())


async def _send_scans_list(message: Message, session: AsyncSession, user_id: int) -> None:
    rows = await scans.recent_scans(session, user_id, limit=BOT_SCANS_LIMIT)
    if not rows:
        await message.answer(texts.MY_SCANS_EMPTY, reply_markup=kb.scan_footer_kb())
        return
    buttons = [
        (row.id, texts.scan_button(
            scans.date_label(row), scans.vibe_title(row),
            scans.found_count(row), len(row.items or []),
        ))
        for row in rows
    ]
    await message.answer(texts.MY_SCANS_TITLE, reply_markup=kb.my_scans_kb(buttons))


@router.message(Command("scans"))
async def cmd_scans(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await _user_from_event(session, message.from_user, None)
    await _send_scans_list(message, session, user.id)


@router.callback_query(F.data == "scans:list")
async def menu_scans(call: CallbackQuery, session: AsyncSession) -> None:
    if call.from_user is None or not isinstance(call.message, Message):
        await call.answer()
        return
    user, _ = await get_or_create_user(
        session, call.from_user.id, call.from_user.username, call.from_user.first_name
    )
    await call.answer()
    await _send_scans_list(call.message, session, user.id)


@router.callback_query(F.data.startswith("scans:open:"))
async def open_scan(call: CallbackQuery, session: AsyncSession) -> None:
    """Сохранённый разбор целиком: фото, те же карточки, без лимита и без vision."""
    if call.from_user is None or not isinstance(call.message, Message) or call.data is None:
        await call.answer()
        return
    raw_id = call.data.rsplit(":", 1)[1]
    scan = (
        await scans.get_scan(session, call.from_user.id, int(raw_id))
        if raw_id.isdigit() else None
    )
    if scan is None:
        await call.answer(texts.SCAN_OUTDATED, show_alert=True)
        return
    await call.answer()

    caption = texts.saved_scan_caption(
        scans.date_label(scan), scan.vibe,
        [(e.get("slot") or "", e.get("name") or "", e.get("color") or "")
         for e in scan.items or []],
    )
    sent = False
    if scan.tg_file_id:
        with suppress(Exception):
            await call.message.answer_photo(scan.tg_file_id, caption=caption[:1024])
            sent = True
    if not sent:
        await call.message.answer(caption)

    await track(session, call.from_user.id, "scan_reopen", {"scan": str(scan.id), "src": "bot"})
    user = await session.get(User, call.from_user.id)
    await _send_scan(call.message, scan, user.search_marketplaces if user else None)
    await call.message.answer(texts.SAVED_SCAN_PRICES_NOTE, reply_markup=kb.scan_footer_kb())


@router.callback_query(F.data == "menu:invite")
async def menu_invite(call: CallbackQuery, session: AsyncSession) -> None:
    """Приглашение подруги: ссылка и текущий счёт скидок."""
    if call.from_user is None or not isinstance(call.message, Message):
        await call.answer()
        return
    user, _ = await get_or_create_user(
        session, call.from_user.id, call.from_user.username, call.from_user.first_name
    )
    settings = get_settings()
    invited = await session.scalar(
        select(func.count()).select_from(User).where(User.invited_by_user_id == user.id)
    )
    link = f"https://t.me/{settings.bot_username}?start=inv_{user.id}"
    await call.message.answer(
        texts.invite_text(
            link,
            int(invited or 0),
            user.referral_credits or 0,
            settings.invite_discount_percent,
            settings.invite_friend_bonus_scans,
        )
    )
    await track(session, user.id, "invite_open")
    await call.answer()


@router.callback_query(F.data == "menu:where")
async def menu_where(call: CallbackQuery, session: AsyncSession) -> None:
    if call.from_user is None or not isinstance(call.message, Message):
        await call.answer()
        return
    user, _ = await get_or_create_user(
        session, call.from_user.id, call.from_user.username, call.from_user.first_name
    )
    await call.message.answer(
        texts.WHERE_SEARCH_TITLE, reply_markup=kb.where_search_kb(user.search_marketplaces)
    )
    await call.answer()


@router.callback_query(F.data.startswith("where:toggle:"))
async def where_toggle(call: CallbackQuery, session: AsyncSession) -> None:
    if call.from_user is None or not isinstance(call.message, Message) or call.data is None:
        await call.answer()
        return
    user = await session.get(User, call.from_user.id)
    if user is None:
        await call.answer()
        return
    code = call.data.rsplit(":", 1)[1]
    if code not in BY_CODE:
        await call.answer()
        return
    chosen = set(parse_codes(user.search_marketplaces))
    if code in chosen:
        chosen.discard(code)
    else:
        chosen.add(code)
    # все выключить нельзя - parse_codes вернёт полный набор, сохраним его же
    user.search_marketplaces = ",".join(parse_codes(",".join(chosen)))
    await session.commit()
    with suppress(Exception):
        await call.message.edit_reply_markup(
            reply_markup=kb.where_search_kb(user.search_marketplaces)
        )
    await call.answer(texts.WHERE_SAVED)


@router.callback_query(F.data.startswith("more:"))
async def more_similar(call: CallbackQuery, session: AsyncSession) -> None:
    """Следующие варианты по вещи из сохранённого разбора, порцией до пяти."""
    if not isinstance(call.message, Message):
        await call.answer()
        return
    found = await _saved_entry(call, session)
    if found is None:
        await call.answer(texts.SCAN_OUTDATED, show_alert=True)
        return
    scan, idx, start, entry = found
    products = entry.get("products") or []
    page = products[start : start + SIMILAR_PAGE]
    if not page:
        await call.answer(texts.NO_MORE_SIMILAR)
        return
    await call.answer()

    rest = start + SIMILAR_PAGE < len(products)
    for n, product in enumerate(page):
        last = n == len(page) - 1
        cap = texts.catalog_card_caption(
            entry.get("slot") or "", product["title"], product["price"], product["store"]
        )
        markup = kb.catalog_card_kb(
            product["buy_url"], product["store"],
            # «Ещё похожие» под последней карточкой порции, если есть что показать
            more_ref=(scan.id, idx, start + SIMILAR_PAGE) if last and rest else None,
        )
        await _answer_card(call.message, cap, product.get("photo_url"), markup)


@router.callback_query(F.data.startswith("notit:"))
async def not_it(call: CallbackQuery, session: AsyncSession) -> None:
    """«Не то» под карточкой: чиним выдачу сейчас и копим разметку на будущее."""
    if not isinstance(call.message, Message) or call.data is None:
        await call.answer()
        return
    try:
        log_id = int(call.data.rsplit(":", 1)[1])
    except ValueError:
        await call.answer()
        return
    row = await record_feedback(session, log_id, "not_it")
    if row is None:
        await call.answer("Спасибо, учла")
        return
    await call.answer(texts.NOT_IT_THANKS, show_alert=False)
    await call.message.answer(
        texts.NOT_IT_HINT,
        reply_markup=kb.lookscan_kb(
            [LookItem(category=row.slot, name=row.query, color="", search_query=row.query)]
        ),
    )


@router.callback_query(F.data.startswith("only:"))
async def only_item(call: CallbackQuery, session: AsyncSession) -> None:
    """Крупно ищем одну вещь из сохранённого разбора."""
    if call.from_user is None or not isinstance(call.message, Message):
        await call.answer()
        return
    found = await _saved_entry(call, session)
    if found is None:
        await call.answer(texts.SCAN_OUTDATED, show_alert=True)
        return
    item = scans.look_of(found[3])
    user = await session.get(User, call.from_user.id)
    raw_codes = user.search_marketplaces if user else None
    await call.message.answer(
        texts.only_item_caption(item.name, item.color),
        reply_markup=kb.only_item_kb(item, raw_codes),
    )
    await call.answer()


@router.callback_query(Survey.size, F.data.startswith("size:"))
async def survey_size(call: CallbackQuery, state: FSMContext) -> None:
    assert call.data is not None
    await state.update_data(size=call.data.split(":", 1)[1])
    await state.set_state(Survey.style)
    if isinstance(call.message, Message):
        await call.message.edit_text(texts.ASK_STYLE, reply_markup=kb.styles_kb())
    await call.answer()


@router.callback_query(Survey.style, F.data.startswith("style:"))
async def survey_style(call: CallbackQuery, state: FSMContext) -> None:
    assert call.data is not None
    await state.update_data(style=call.data.split(":", 1)[1])
    await state.set_state(Survey.budget)
    if isinstance(call.message, Message):
        await call.message.edit_text(texts.ASK_BUDGET, reply_markup=kb.budgets_kb())
    await call.answer()


@router.callback_query(Survey.budget, F.data.startswith("budget:"))
async def survey_budget(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    assert call.data is not None and call.from_user is not None
    data = await state.get_data()
    await state.clear()

    user = await session.get(User, call.from_user.id)
    if user is None:
        return
    user.size = data.get("size")
    user.style = data.get("style")
    user.budget = call.data.split(":", 1)[1]
    user.survey_done = True
    await session.commit()
    await track(
        session,
        user.id,
        "survey_done",
        {"size": user.size or "", "style": user.style or "", "budget": user.budget or ""},
    )
    if isinstance(call.message, Message):
        await call.message.edit_text(texts.SURVEY_DONE)
        await _send_selection(call.message, session, user)
    await call.answer()


@router.callback_query(F.data.in_({"outfit:more", "outfit:next"}))
async def more_variants(call: CallbackQuery, session: AsyncSession) -> None:
    """Новая превью-подборка. Бесплатно, лимит не тратит. outfit:next - алиас старых кнопок."""
    if call.from_user is None or not isinstance(call.message, Message):
        await call.answer()
        return
    user = await session.get(User, call.from_user.id)
    if user is None:
        await call.answer()
        return
    await _send_selection(call.message, session, user)
    await call.answer()


@router.callback_query(F.data.startswith("outfit:pick:"))
async def pick_outfit(call: CallbackQuery, session: AsyncSession) -> None:
    """Раскрытие образа: состав, цены, кнопки покупки. Списывает фри-лимит."""
    if call.from_user is None or not isinstance(call.message, Message) or call.data is None:
        await call.answer()
        return
    user = await session.get(User, call.from_user.id)
    if user is None:
        await call.answer()
        return

    outfit = await session.get(Outfit, int(call.data.rsplit(":", 1)[1]))
    if outfit is None or outfit.status != "published":
        await call.message.answer(texts.NO_OUTFITS)
        await call.answer()
        return

    settings = get_settings()
    already_seen = await session.get(UserOutfitView, (user.id, outfit.id)) is not None
    if not already_seen and not await can_view_new_outfit(session, user.id, settings.free_limit):
        price = price_for(user.id)
        await track(session, user.id, "paywall_view", {"price": str(price)})
        markup = kb.paywall_kb(pay_url_for(user.id))
        await call.message.answer(texts.paywall_text(price), reply_markup=markup)
        await call.answer()
        return

    await register_view(session, user.id, outfit.id)
    await track(session, user.id, "outfit_view", {"outfit": outfit.slug})

    caption = texts.outfit_caption(outfit)
    markup = kb.outfit_kb(outfit)
    if outfit.cover_photo:
        try:
            await call.message.answer_photo(
                _photo_input(outfit.cover_photo), caption=caption, reply_markup=markup
            )
        except Exception:
            await call.message.answer(caption, reply_markup=markup)
    else:
        await call.message.answer(caption, reply_markup=markup)
    await call.answer()
