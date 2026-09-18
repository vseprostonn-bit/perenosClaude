"""Демо-данные для проверки бота, пока нет реального каталога.

Запуск: .venv/bin/python -m scripts.seed_demo
Повторный запуск обновляет обложки образов из assets/demo/<style>.*
Удалить при наполнении реальными образами (фаза B плана).
"""

import asyncio
from glob import glob
from pathlib import Path

from sqlalchemy import select

from app.db import session_scope
from app.models import Base, Blogger, Item, Outfit, OutfitItem

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def cover_for(style: str) -> str | None:
    found = glob(str(PROJECT_ROOT / "assets" / "demo" / f"{style}.*"))
    return str(Path(found[0]).relative_to(PROJECT_ROOT)) if found else None


async def main() -> None:
    from app.db import get_session_factory

    factory = get_session_factory()
    engine = factory.kw["bind"]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_scope() as session:
        existing = await session.scalar(select(Outfit.id).limit(1))
        if existing is not None:
            updated = 0
            for outfit in (await session.scalars(select(Outfit))).all():
                cover = cover_for(outfit.style)
                if cover and outfit.cover_photo != cover:
                    outfit.cover_photo = cover
                    updated += 1
            await session.commit()
            print(f"Демо-данные уже есть; обложек обновлено: {updated}")
            return

        session.add(Blogger(name="Демо-блогер", promo_code="demo"))

        catalog = [
            ("casual", "mid", "Кэжуал на каждый день", [
                ("top", "Свитшот оверсайз", 2490, "lamoda"),
                ("bottom", "Джинсы прямые", 3290, "wb"),
                ("shoes", "Кеды белые", 4190, "lamoda"),
            ]),
            ("office", "high", "Офис: мягкая классика", [
                ("top", "Жакет удлинённый", 7990, "lamoda"),
                ("bottom", "Брюки палаццо", 4590, "ozon"),
                ("shoes", "Лоферы кожаные", 8990, "lamoda"),
            ]),
            ("date", "mid", "Свидание в городе", [
                ("top", "Топ с открытой спиной", 1890, "wb"),
                ("bottom", "Юбка-миди атласная", 2790, "wb"),
                ("shoes", "Босоножки на каблуке", 5490, "ym"),
            ]),
            ("basic", "low", "База: капсула старт", [
                ("top", "Футболка белая", 890, "wb"),
                ("bottom", "Джинсы мом", 2190, "wb"),
                ("shoes", "Кроссовки базовые", 2990, "ozon"),
            ]),
            ("sport", "mid", "Спорт-шик на прогулку", [
                ("top", "Зип-худи", 2690, "ozon"),
                ("bottom", "Джоггеры", 1990, "wb"),
                ("shoes", "Кроссовки массивные", 6490, "lamoda"),
            ]),
        ]

        for idx, (style, budget, title, items) in enumerate(catalog, start=1):
            outfit = Outfit(
                slug=f"demo-{idx}",
                title=title,
                style=style,
                budget_tier=budget,
                cover_photo=cover_for(style),
                status="published",
                author="demo",
            )
            session.add(outfit)
            await session.flush()
            for pos, (slot, name, price, source) in enumerate(items):
                item = Item(
                    source=source,
                    external_id=f"demo-{idx}-{pos}",
                    title=name,
                    category=slot,
                    price=price,
                    product_url="https://www.lamoda.ru/",
                )
                session.add(item)
                await session.flush()
                session.add(
                    OutfitItem(outfit_id=outfit.id, item_id=item.id, slot=slot, position=pos)
                )
        await session.commit()
        print("Демо: 5 образов + блогер promo_code=demo")


if __name__ == "__main__":
    asyncio.run(main())
