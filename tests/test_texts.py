from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item, Outfit, OutfitItem
from app.texts import outfit_caption


async def test_caption_keeps_commas_in_titles(session: AsyncSession) -> None:
    item = Item(
        source="wb",
        external_id="c1",
        title="Джинсы, синие",
        category="bottom",
        price=2990,
        product_url="https://example.com/1",
    )
    session.add(item)
    await session.flush()
    outfit = Outfit(slug="c", title="Тест", style="casual", budget_tier="mid", status="published")
    session.add(outfit)
    await session.flush()
    session.add(OutfitItem(outfit_id=outfit.id, item_id=item.id, slot="bottom"))
    await session.commit()

    session.expunge_all()  # как в проде: бот получает образ свежим запросом
    loaded = await session.scalar(select(Outfit).where(Outfit.id == outfit.id))
    assert loaded is not None
    caption = outfit_caption(loaded)
    assert "Джинсы, синие" in caption
    assert "2 990 р" in caption
    assert "Весь образ: 2 990 р" in caption
