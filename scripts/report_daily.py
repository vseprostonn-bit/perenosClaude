"""Ежедневный отчёт воронки владельцу в TG. Сутки считаются по МСК.

Запуск (сервер, cron 09:00 МСК): .venv/bin/python -m scripts.report_daily
Без ADMIN_TG_ID печатает отчёт в stdout.
"""

import asyncio
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import func, select

from app.config import get_settings
from app.db import session_scope
from app.models import Event, Payment, User

MSK = timezone(timedelta(hours=3))


def yesterday_bounds_utc() -> tuple[datetime, datetime, str]:
    now_msk = datetime.now(MSK)
    day_start_msk = now_msk.replace(hour=0, minute=0, second=0, microsecond=0)
    start_msk = day_start_msk - timedelta(days=1)
    label = start_msk.strftime("%d.%m.%Y")
    return start_msk.astimezone(UTC), day_start_msk.astimezone(UTC), label


async def build_report() -> str:
    start, end, label = yesterday_bounds_utc()
    async with session_scope() as session:
        async def count_event(name: str) -> int:
            value = await session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.name == name, Event.ts >= start, Event.ts < end)
            )
            return int(value or 0)

        new_users = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.created_at >= start, User.created_at < end)
        )
        ref_users = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.created_at >= start,
                User.created_at < end,
                User.referrer_blogger_id.is_not(None),
            )
        )
        paid_count = await session.scalar(
            select(func.count())
            .select_from(Payment)
            .where(Payment.status == "paid", Payment.paid_at >= start, Payment.paid_at < end)
        )
        paid_sum = await session.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == "paid", Payment.paid_at >= start, Payment.paid_at < end
            )
        )

        lines = [
            f"ОБРАЗ - воронка за {label} (МСК)",
            "",
            f"Новые регистрации: {int(new_users or 0)} (из них по рефкам: {int(ref_users or 0)})",
            f"Анкет пройдено: {await count_event('survey_done')}",
            f"Показов подборок: {await count_event('selection_view')}",
            f"Раскрытий образов: {await count_event('outfit_view')}",
            f"Показов пейвола: {await count_event('paywall_view')}",
            f"Кликов «оплатить»: {await count_event('paywall_click')}",
            f"Оплат: {int(paid_count or 0)} на {int(paid_sum or 0)} р",
        ]
        return "\n".join(lines)


def _recipients() -> list[int]:
    """admin_tg_id + report_tg_ids, без нулей и дублей, порядок сохраняется."""
    settings = get_settings()
    ids: list[int] = []
    if settings.admin_tg_id:
        ids.append(settings.admin_tg_id)
    for raw in (settings.report_tg_ids or "").replace(" ", "").split(","):
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if value:
            ids.append(value)
    seen: set[int] = set()
    unique: list[int] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            unique.append(i)
    return unique


async def main() -> None:
    report = await build_report()
    recipients = _recipients()
    token = get_settings().bot_token
    if recipients and token:
        from aiogram import Bot

        bot = Bot(token=token)
        try:
            for chat_id in recipients:
                try:
                    await bot.send_message(chat_id, report)
                except Exception as exc:  # noqa: BLE001 - один сбойный получатель не рвёт рассылку
                    print(f"fail {chat_id}: {exc}")
                else:
                    print(f"sent {chat_id}")
        finally:
            await bot.session.close()
    else:
        print(report)


if __name__ == "__main__":
    asyncio.run(main())
