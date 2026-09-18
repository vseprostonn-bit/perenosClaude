"""Добавление блогерки/админа канала в реф-систему.

Запуск на сервере:
  .venv/bin/python -m scripts.add_blogger --name "Вика" --tg vika_nn --code vika
  .venv/bin/python -m scripts.add_blogger --list

Печатает готовую реф-ссылку для поста.
"""

import argparse
import asyncio

from sqlalchemy import select

from app.db import session_scope
from app.models import Blogger

BOT_LINK = "https://t.me/obraz_style_bot?start=ref_{code}"


async def add(name: str, tg: str, code: str, percent: int, months: int) -> None:
    async with session_scope() as session:
        existing = await session.scalar(select(Blogger).where(Blogger.promo_code == code))
        if existing is not None:
            print(f"Код '{code}' уже занят: {existing.name} (@{existing.tg_username})")
            print(f"Ссылка: {BOT_LINK.format(code=code)}")
            return
        blogger = Blogger(
            name=name,
            tg_username=tg.lstrip("@"),
            promo_code=code,
            percent=percent,
            rev_months=months,
        )
        session.add(blogger)
        await session.commit()
        print(f"Добавлена: {name} (@{blogger.tg_username}), {percent}% на {months} мес")
        print(f"Реф-ссылка: {BOT_LINK.format(code=code)}")
        print("Статистика для неё в боте: команда /stats (с её TG-аккаунта)")


async def list_all() -> None:
    async with session_scope() as session:
        bloggers = (await session.scalars(select(Blogger).order_by(Blogger.id))).all()
        if not bloggers:
            print("Блогерок пока нет")
            return
        for b in bloggers:
            print(f"#{b.id} {b.name} @{b.tg_username} code={b.promo_code} "
                  f"{b.percent}%/{b.rev_months}мес -> {BOT_LINK.format(code=b.promo_code)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Реф-система: блогерки")
    parser.add_argument("--list", action="store_true", help="показать всех")
    parser.add_argument("--name", help="имя")
    parser.add_argument("--tg", help="tg-ник без @")
    parser.add_argument("--code", help="промокод (латиницей, без ref_)")
    parser.add_argument("--percent", type=int, default=15)
    parser.add_argument("--months", type=int, default=6)
    args = parser.parse_args()

    if args.list:
        asyncio.run(list_all())
        return
    if not (args.name and args.tg and args.code):
        parser.error("нужны --name, --tg и --code (или --list)")
    asyncio.run(add(args.name, args.tg, args.code.lower(), args.percent, args.months))


if __name__ == "__main__":
    main()
