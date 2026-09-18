"""События воронки. Каждое действие пишется - на них строится отчёт go/no-go."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event


async def track(
    session: AsyncSession,
    user_id: int | None,
    name: str,
    payload: dict[str, str] | None = None,
) -> None:
    session.add(Event(user_id=user_id, name=name, payload=payload))
    await session.commit()
