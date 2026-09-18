"""Генерирует обложки готовых образов через YandexART и проставляет cover_photo.

Промпт собирается из состава образа - обложка совпадает с вещами.
Запуск: cd ~/obraz-app && .venv/bin/python -m scripts.gen_covers
Повторный запуск перерисовывает только образы без обложки (--force - все).
"""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

from app.db import session_scope
from app.models import Outfit
from app.services.artgen import generate_cover
from app.texts import CATEGORY_NAMES, SLOT_NAMES

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COVERS_DIR = PROJECT_ROOT / "assets" / "demo"


def prompt_for(outfit: Outfit) -> str:
    parts = []
    for oi in outfit.items:
        slot = SLOT_NAMES.get(oi.slot, CATEGORY_NAMES.get(oi.slot, oi.slot))
        parts.append(f"{slot.lower()}: {oi.item.title.lower()}")
    return f"женский образ «{outfit.title}»: " + ", ".join(parts)


async def main() -> None:
    force = "--force" in sys.argv
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    async with session_scope() as session:
        outfits = (await session.scalars(select(Outfit))).all()
        done, skipped, failed = 0, 0, 0
        for outfit in outfits:
            if outfit.cover_photo and not force:
                skipped += 1
                continue
            image = await generate_cover(prompt_for(outfit))
            if image is None:
                print(f"[fail] {outfit.slug}")
                failed += 1
                continue
            target = COVERS_DIR / f"{outfit.style}.jpg"
            target.write_bytes(image)
            outfit.cover_photo = str(target.relative_to(PROJECT_ROOT))
            done += 1
            print(f"[ok] {outfit.slug} -> {outfit.cover_photo}")
        await session.commit()
    print(f"готово: {done}, пропущено: {skipped}, ошибок: {failed}")


if __name__ == "__main__":
    asyncio.run(main())
