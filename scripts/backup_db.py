"""Ежедневный бэкап базы: локальная копия с ротацией + документ владельцу в TG.

Запуск (сервер, cron 00:30 UTC = 03:30 МСК):
cd ~/obraz-app && .venv/bin/python -m scripts.backup_db
"""

import asyncio
import gzip
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from app.config import get_settings

MSK = timezone(timedelta(hours=3))
BACKUP_DIR = Path.home() / "obraz-backups"
KEEP_DAYS = 14


def db_path() -> Path:
    return Path(get_settings().database_url.rsplit("///", 1)[-1])


def make_backup() -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    target = BACKUP_DIR / f"obraz-{datetime.now(MSK):%Y-%m-%d}.db.gz"
    tmp = BACKUP_DIR / "obraz-tmp.db"
    src = sqlite3.connect(db_path())
    dst = sqlite3.connect(tmp)
    with dst:
        src.backup(dst)  # консистентная копия даже при живом боте
    dst.close()
    src.close()
    with open(tmp, "rb") as f_in, gzip.open(target, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    tmp.unlink()
    return target


def rotate() -> int:
    cutoff = datetime.now(UTC) - timedelta(days=KEEP_DAYS)
    removed = 0
    for f in BACKUP_DIR.glob("obraz-*.db.gz"):
        if datetime.fromtimestamp(f.stat().st_mtime, UTC) < cutoff:
            f.unlink()
            removed += 1
    return removed


async def send_to_owner(path: Path) -> None:
    settings = get_settings()
    if not (settings.admin_tg_id and settings.bot_token):
        return
    from aiogram import Bot
    from aiogram.types import FSInputFile

    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_document(
            settings.admin_tg_id,
            FSInputFile(path),
            caption=f"Бэкап базы «Образ», {datetime.now(MSK):%d.%m.%Y}",
            disable_notification=True,
        )
    finally:
        await bot.session.close()


async def main() -> None:
    target = make_backup()
    removed = rotate()
    await send_to_owner(target)
    print(f"backup: {target.name} ({target.stat().st_size} b), rotated out: {removed}")


if __name__ == "__main__":
    asyncio.run(main())
