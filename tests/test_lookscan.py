import json

from sqlalchemy.ext.asyncio import AsyncSession

from app import texts
from app.bot.keyboards import lookscan_kb
from app.config import get_settings
from app.services.events import track
from app.services.lookscan import SCAN_EVENT, can_scan, parse_analysis
from app.services.users import get_or_create_user
from tests.conftest import make_subscription

RAW = json.dumps(
    {
        "is_outfit": True,
        "vibe": "Тихая роскошь",
        "items": [
            {
                "category": "outerwear",
                "name": "тренч оверсайз",
                "color": "бежевый",
                "search_query": "тренч оверсайз бежевый",
            },
            {
                "category": "shoes",
                "name": "лоферы",
                "color": "чёрный",
                "search_query": "лоферы чёрные кожаные",
            },
        ],
    }
)


def test_parse_analysis_ok() -> None:
    analysis = parse_analysis(RAW)
    assert analysis is not None and analysis.is_outfit
    assert analysis.vibe == "Тихая роскошь"
    assert [i.category for i in analysis.items] == ["outerwear", "shoes"]


def test_parse_analysis_garbage() -> None:
    assert parse_analysis("не json") is None
    assert parse_analysis('{"is_outfit": true}') is None


def test_parse_analysis_markdown_wrapped() -> None:
    wrapped = f"Вот разбор:\n```json\n{RAW}\n```"
    analysis = parse_analysis(wrapped)
    assert analysis is not None and len(analysis.items) == 2


def test_parse_analysis_not_outfit() -> None:
    analysis = parse_analysis('{"is_outfit": false, "vibe": "", "items": []}')
    assert analysis is not None and not analysis.is_outfit and analysis.items == []


def test_caption_and_keyboard() -> None:
    analysis = parse_analysis(RAW)
    assert analysis is not None
    caption = texts.lookscan_caption(
        analysis.vibe, [(i.category, i.name, i.color) for i in analysis.items]
    )
    assert "Верхняя одежда: тренч оверсайз, бежевый" in caption
    assert "тихая роскошь" in caption

    markup = lookscan_kb(analysis.items)
    assert len(markup.inline_keyboard) == 3  # 2 вещи + «показать образы»
    wb_url = markup.inline_keyboard[0][0].url
    assert wb_url is not None and "wildberries.ru" in wb_url and "%20" in wb_url


async def test_free_user_gets_one_scan(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, 900, "u", "U")
    assert await can_scan(session, user.id, subscribed=False)
    await track(session, user.id, SCAN_EVENT, {})
    assert not await can_scan(session, user.id, subscribed=False)


async def test_subscriber_daily_limit(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, 901, "u", "U")
    await make_subscription(session, user.id)
    limit = get_settings().lookscan_daily_limit
    for _ in range(limit - 1):
        await track(session, user.id, SCAN_EVENT, {})
    assert await can_scan(session, user.id, subscribed=True)
    await track(session, user.id, SCAN_EVENT, {})
    assert not await can_scan(session, user.id, subscribed=True)
