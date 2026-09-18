"""Дев-запуск бота в polling-режиме: python -m app.bot.run.

На VPS перейдём на webhook внутри FastAPI (фаза F плана).
"""

import asyncio
import logging
import threading

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from app.bot.handlers import router
from app.bot.keyboards import miniapp_url
from app.bot.middleware import DbSessionMiddleware
from app.config import get_settings
from app.db import ensure_schema, get_session_factory
from app.services import embeddings

COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="scan", description="Разобрать лук по фото"),
    BotCommand(command="scans", description="Мои разборы"),
    BotCommand(command="outfits", description="Готовые образы"),
    BotCommand(command="premium", description="Подписка"),
    BotCommand(command="help", description="Как это работает"),
]


log = logging.getLogger(__name__)


async def main() -> None:
    # Время в каждой строке: без него по bot.log нельзя понять, когда бот
    # упал и совпало ли это с падением сайта.
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN пуст: создай бота у @BotFather и заполни .env")

    await ensure_schema()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.update.middleware(DbSessionMiddleware(get_session_factory()))
    dp.include_router(router)

    # Меню и кнопка приложения - косметика. Если Telegram на старте не ответил,
    # бот всё равно должен начать принимать сообщения, а не упасть целиком.
    try:
        await bot.set_my_commands(COMMANDS)
        # Кнопка мини-аппа рядом со строкой ввода - главный вход в приложение.
        if miniapp_url():
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Приложение", web_app=WebAppInfo(url=miniapp_url())
                )
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("не выставил меню бота, продолжаю без него: %s", exc)
    # Прогрев CLIP в фоне: первый разбор в боте иначе ждёт ~20с загрузки весов.
    threading.Thread(target=embeddings.preload, daemon=True).start()
    log.info("бот запущен, polling")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
