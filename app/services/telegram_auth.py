"""Проверка initData мини-аппа.

Telegram отдаёт странице строку initData с данными пользователя и подписью.
Доверять ей на слово нельзя: она приходит из браузера, её может подделать кто
угодно. Подпись проверяется по алгоритму из документации Telegram:

    secret = HMAC_SHA256(key="WebAppData", msg=bot_token)
    hash   = HMAC_SHA256(key=secret, msg="\\n".join(sorted("k=v")))

Без валидной подписи мини-апп не получает ничего: ни профиля, ни разборов.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from app.config import get_settings

# Сколько живёт подпись. Сутки - компромисс: дольше опасно, короче неудобно
# при открытом на весь день приложении.
MAX_AGE_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class TelegramUser:
    id: int
    username: str | None
    first_name: str | None


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def verify_init_data(init_data: str, bot_token: str | None = None,
                     max_age: int = MAX_AGE_SECONDS) -> TelegramUser | None:
    """Разбирает и проверяет initData. None - подпись не сошлась или данные протухли."""
    token = bot_token if bot_token is not None else get_settings().bot_token
    if not init_data or not token:
        return None

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    expected = hmac.new(_secret_key(token), check_string.encode(), hashlib.sha256).hexdigest()
    # сравнение постоянного времени: иначе подпись подбирается по времени ответа
    if not hmac.compare_digest(expected, received_hash):
        return None

    if max_age:
        try:
            auth_date = int(pairs.get("auth_date", "0"))
        except ValueError:
            return None
        if auth_date <= 0 or time.time() - auth_date > max_age:
            return None

    try:
        user = json.loads(pairs.get("user", "{}"))
        user_id = int(user["id"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None

    return TelegramUser(
        id=user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
    )


def build_init_data(user_id: int, bot_token: str, username: str = "test",
                    first_name: str = "Тест", auth_date: int | None = None) -> str:
    """Собирает подписанную initData. Нужна тестам и ручной проверке эндпоинтов."""
    payload = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAA",
        "user": json.dumps(
            {"id": user_id, "username": username, "first_name": first_name},
            ensure_ascii=False, separators=(",", ":"),
        ),
    }
    check_string = "\n".join(f"{k}={payload[k]}" for k in sorted(payload))
    signature = hmac.new(_secret_key(bot_token), check_string.encode(), hashlib.sha256).hexdigest()
    from urllib.parse import urlencode

    return urlencode({**payload, "hash": signature})
