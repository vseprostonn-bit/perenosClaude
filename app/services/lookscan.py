"""«Скрин в образ»: ИИ-разбор фото лука на вещи (GigaChat vision).

Модель возвращает не строку с названием, а паспорт вещи: тип, силуэт, длина,
рукав, вырез, посадка, принт - значения только из закрытых словарей
`app.services.attributes`. По свободному тексту вещи сопоставить нельзя:
«рубашка оверсайз молочная» и «рубашка приталенная белая» отличаются лишь
словами, которых нет в названии каталожной карточки.

Методология - docs/metodologiya-matchinga-2026-09-03.md
"""


import asyncio
from datetime import UTC, datetime, timedelta, timezone

import httpx
from gigachat import GigaChat
from gigachat.exceptions import GigaChatException
from gigachat.models import (
    ChatCompletionRequest,
    ChatContentFile,
    ChatContentPart,
    ChatMessage,
)
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Event
from app.services import attributes

SCAN_EVENT = "look_scan"
MSK = timezone(timedelta(hours=3))

# Ниже этого порога уверенности vision вещь считаем невидимой/выдуманной и не
# показываем: лучше не предложить, чем уверенно показать не ту (выдуманную) вещь.
MIN_ITEM_CONFIDENCE = 0.4
# Сумка, обувь и аксессуары - самые частые выдумки модели: «образ» стереотипно
# включает их, даже когда в кадре их нет. Для этих слотов планка выше.
MIN_CONFIDENCE_BY_SLOT = {"bag": 0.6, "accessory": 0.6, "shoes": 0.55}


def item_visible(look: "LookItem") -> bool:
    """Показывать ли вещь. Порог зависит от слота: аксессуары выдумываются чаще."""
    threshold = MIN_CONFIDENCE_BY_SLOT.get(look.category, MIN_ITEM_CONFIDENCE)
    return look.confidence >= threshold


def catalog_gender(look_gender: str, profile_gender: str | None = None) -> str | None:
    """Пол каталога для поиска.

    unisex НЕ схлопываем в женский: мужской лук из джинсов, худи и кроссовок
    модель часто помечает как unisex, и тогда мужчина получал женские вещи.
    Если модель не уверена - берём пол из профиля, а если и его нет, ищем без
    фильтра и отдаём решение ранжированию.
    """
    if look_gender in ("men", "women"):
        return look_gender
    if profile_gender in ("men", "women"):
        return profile_gender
    return None

def _prompt() -> str:
    """Промпт собирается из словарей: единственный источник допустимых значений."""
    values = attributes.allowed_values()
    listing = "\n".join(
        f"  {field}: {', '.join(vals)}" for field, vals in values.items()
    )
    return (
        "Ты стилист сервиса «Образ». На фото - лук (образ) с Pinterest или из соцсетей. "
        "Сначала определи gender: women (женский образ), men (мужской) или unisex. "
        "Разложи лук на вещи. Для каждой вещи дай:\n"
        "category - одно из top, bottom, dress, outerwear, shoes, bag, accessory;\n"
        "name - короткое русское название с фасоном (например «тренч оверсайз двубортный»);\n"
        "color - цвет по-русски;\n"
        "search_query - поисковый запрос для маркетплейса: категория + фасон + цвет, "
        "без брендов и без слов про пол, 3-5 слов;\n"
        "type, silhouette, length, sleeve, neckline, fit, pattern - ТОЛЬКО значения "
        "из списка ниже, дословно. Если признак не виден на фото или неприменим к вещи - "
        "поставь null. Не придумывай значений, которых нет в списке:\n"
        f"{listing}\n"
        "details - список коротких деталей, которые видно (например «двубортный», "
        "«пояс», «накладные карманы»), максимум три;\n"
        "confidence - от 0 до 1, насколько уверенно вещь видно на фото. "
        "Мелкую, перекрытую или размытую вещь оценивай ниже 0.5.\n"
        "vibe - одна фраза, какое настроение у образа. Если на фото нет одежды или "
        "образ не разобрать - is_outfit=false, пустой items, gender=unisex. Украшения "
        "мельче сумки и очки пропускай, если они не главный акцент. "
        "НЕ добавляй вещь, которой на фото не видно: если кадр обрезан и ног/обуви "
        "или головы нет - не выдумывай обувь или головной убор, показывай только "
        "реально видимое. Лучше меньше вещей, чем выдуманные. Обрезанную кадром, "
        "мелкую или размытую вещь оценивай confidence ниже 0.4.\n"
        "ОТДЕЛЬНО про сумку, обувь и аксессуары: их придумывают чаще всего, потому "
        "что «образ» стереотипно из них состоит. Добавляй их, только если предмет "
        "прямо виден в кадре. Не видно сумки - значит сумки нет, и это нормальный "
        "ответ. Пустой список лучше выдуманной вещи.\n"
        "Пол определяй по человеку на фото, а не по вещам. Мужской лук из джинсов, "
        "худи и кроссовок - это men, а не unisex. unisex ставь только если по кадру "
        "действительно нельзя понять. "
        "Ответь строго JSON без пояснений."
    )


# Совместимость: часть кода и тестов ссылается на PROMPT как на строку.
PROMPT = _prompt()


class LookItem(BaseModel):
    """Вещь с фото. Новые поля опциональны: старые разборы и тесты не ломаются."""

    category: str
    name: str
    color: str
    search_query: str

    # паспорт вещи, значения из attributes.ATTRIBUTE_DICTS
    type: str | None = None
    silhouette: str | None = None
    length: str | None = None
    sleeve: str | None = None
    neckline: str | None = None
    fit: str | None = None
    pattern: str | None = None
    details: list[str] = []
    # 0.5, а не 1.0: если модель поле не вернула, это «не знаю», а не
    # «уверена на сто процентов». Прежний дефолт пропускал выдуманные вещи.
    confidence: float = 0.5

    def passport(self) -> attributes.Attributes:
        """Паспорт вещи. Пустые поля добираются из названия - модель их иногда пропускает."""
        from_title = attributes.parse_title(f"{self.name} {self.search_query}")
        return attributes.Attributes(
            type=self.type or from_title.type,
            silhouette=self.silhouette or from_title.silhouette,
            length=self.length or from_title.length,
            sleeve=self.sleeve or from_title.sleeve,
            neckline=self.neckline or from_title.neckline,
            fit=self.fit or from_title.fit,
            pattern=self.pattern or from_title.pattern,
            details=list(self.details),
        )


class LookAnalysis(BaseModel):
    # is_outfit модель часто НЕ возвращает, когда образ на фото есть: в промпте про
    # это поле сказано только для случая «одежды нет». Раньше пропуск обязательного
    # поля рушил валидацию целиком -> разбор падал у ~3 фото из 4, и пользователь
    # видел «не получилось разобрать» на нормальном фото. По умолчанию считаем, что
    # образ есть; пустой items ниже по коду и так трактуется как «не разобрать».
    is_outfit: bool = True
    vibe: str = ""  # настроение образа - косметика, пропуск не должен валить разбор
    gender: str = "women"  # women | men | unisex
    items: list[LookItem]


_client: GigaChat | None = None


def _get_client() -> GigaChat:
    global _client
    if _client is None:
        # verify_ssl_certs=False: у Сбера сертификат НУЦ Минцифры, его нет в системных CA
        _client = GigaChat(
            credentials=get_settings().gigachat_credentials,
            verify_ssl_certs=False,
            timeout=60,
        )
    return _client


def parse_analysis(raw: str) -> LookAnalysis | None:
    """Достаёт JSON из ответа модели (включая обёртки ```json ... ```)."""
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return LookAnalysis.model_validate_json(text[start : end + 1])
    except ValidationError:
        return None


async def analyze_look(image: bytes) -> LookAnalysis | None:
    """Разбирает фото лука (jpeg из Telegram). None - ошибка API или битый ответ.

    GigaChat периодически рвёт keep-alive соединение
    (`httpx.RemoteProtocolError: Server disconnected without sending a response`):
    синглтон-клиент переиспользует сокет, который сервер уже закрыл по таймауту.
    Библиотечный ретрай на это не реагирует, и разбор рандомно падает - у бота
    пользователь видит «не получилось разобрать», хотя фото нормальное. Поэтому на
    сетевой обрыв роняем протухший клиент и пробуем заново свежим.
    """
    global _client
    response = None
    for attempt in range(3):
        client = _get_client()
        try:
            uploaded = await client.aupload_file(("look.jpg", image, "image/jpeg"))
            payload = ChatCompletionRequest(
                model=get_settings().lookscan_model,
                messages=[
                    ChatMessage(
                        role="user",
                        content=[
                            ChatContentPart(files=[ChatContentFile(id=uploaded.id_)]),
                            ChatContentPart(text=_prompt()),
                        ],
                    )
                ],
            )
            response = await client.achat.create(payload)
            break
        except (GigaChatException, ValueError):
            return None
        except httpx.HTTPError:
            _client = None  # протухший пул - следующий заход возьмёт свежий клиент
            if attempt == 2:
                return None
            await asyncio.sleep(0.5 * (attempt + 1))
    if response is None:
        return None
    content = response.messages[0].content if response.messages else None
    if isinstance(content, str):
        raw = content
    elif content:
        raw = " ".join(part.text or "" for part in content)
    else:
        raw = ""
    return parse_analysis(raw)


async def scans_count(
    session: AsyncSession, user_id: int, since: datetime | None = None
) -> int:
    query = (
        select(func.count())
        .select_from(Event)
        .where(Event.user_id == user_id, Event.name == SCAN_EVENT)
    )
    if since is not None:
        query = query.where(Event.ts >= since)
    return int(await session.scalar(query) or 0)


def is_owner(user_id: int) -> bool:
    """Владелец или тестировщик из .env. Лимиты на них не распространяются."""
    settings = get_settings()
    ids = {settings.admin_tg_id} if settings.admin_tg_id else set()
    for raw in (settings.owner_tg_ids or "").replace(" ", "").split(","):
        if raw.isdigit():
            ids.add(int(raw))
    return user_id in ids


async def free_scans_for(session: AsyncSession, user_id: int) -> int:
    """Сколько бесплатных разборов положено. Пришедшей по приглашению - больше."""
    from app.models import User

    settings = get_settings()
    allowance = settings.lookscan_free_scans
    user = await session.get(User, user_id)
    if user is not None and user.invited_by_user_id is not None:
        allowance += settings.invite_friend_bonus_scans
    return allowance


async def can_scan(session: AsyncSession, user_id: int, subscribed: bool) -> bool:
    """Без подписки - бесплатные разборы; с подпиской - дневной лимит по МСК.

    Владельцам лимит не считаем: продукт надо проверять перед каждой публикацией,
    а на трёх бесплатных разборах это невозможно.
    """
    settings = get_settings()
    if is_owner(user_id):
        return True
    if not subscribed:
        allowance = await free_scans_for(session, user_id)
        return await scans_count(session, user_id) < allowance
    day_start_msk = datetime.now(MSK).replace(hour=0, minute=0, second=0, microsecond=0)
    daily = await scans_count(session, user_id, since=day_start_msk.astimezone(UTC))
    return daily < settings.lookscan_daily_limit
