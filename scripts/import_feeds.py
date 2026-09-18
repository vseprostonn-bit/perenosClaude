"""Импорт товарных фидов Admitad в каталог (Item).

Ссылки фидов - в data/admitad_feeds.txt (по одной на строку, в git не коммитим:
содержат приватный код выгрузки). Запуск:
cd ~/obraz-app && .venv/bin/python -m scripts.import_feeds
"""

import asyncio
import re
import urllib.request
from pathlib import Path

from sqlalchemy import select, update

from app.db import session_scope
from app.models import Item
from app.services.feed_import import parse_feed

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEEDS_FILE = PROJECT_ROOT / "data" / "admitad_feeds.txt"

# feed_id -> (код магазина, пол бренда по умолчанию). Дефолт применяется, когда
# у товара нет явной метки пола (fi.gender == unisex). Имя из XML для крупных
# фидов ненадёжно, поэтому источник задаём по feed_id.
FEED_META: dict[str, tuple[str, str | None]] = {
    "26221": ("finnflare", "women"),
    "22535": ("befree", "women"),
    "25654": ("incantoeu", "women"),
    "14764": ("loverepublic", "women"),
    "24700": ("sela", "women"),
    "26118": ("tsum", None),  # универмаг: пол берём из товара
    "25851": ("kanzler", "men"),
    # добавлены 07.09: смешанные магазины (пол по-русски в товаре) -> дефолт None
    "25414": ("street-beat", None),  # кроссовки/стритвир, ~50k
    "26327": ("sportmaster", None),  # спорт, ~20k
    "19982": ("baon", None),         # верхняя одежда, ~9k
    "25158": ("ostin", None),        # казуал, ~5k
    # добавлены 15.09
    "26857": ("gloriajeans", None),  # Gloria Jeans: семейный, ~7k, много детского -> пол из товара
    "26108": ("ekonika", "women"),   # Эконика: женская обувь/сумки/аксессуары, ~1.5k
    # добавлены 16.09: женская мода. 2mood/waistline фид пол не размечает (всё
    # unisex), но по ассортименту марки женские -> дефолт women. LS.NET размечает
    # сам (women/men) -> None, мужское отфильтруется для наших пользовательниц.
    "25132": ("2moodstore", "women"),  # 2MOOD: верх/низ/платья/верхняя, ~2.5k
    "26672": ("waistline", "women"),   # Waistline: женский верх + платья, ~0.8k
    "25079": ("lsnet", None),          # LS.NET.RU: люкс (Armani/Versace), ~466 жен из 1.5k
}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "obraz-import/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def feed_meta(url: str) -> tuple[str, str | None]:
    m = re.search(r"feed_id=(\d+)", url)
    fid = m.group(1) if m else ""
    return FEED_META.get(fid, (f"feed{fid}", None))


def _clean_xml(xml: bytes) -> bytes:
    # крупные фиды иногда приходят с битым хвостом (обрыв на многобайтном символе)
    # -> декодируем терпимо и обрезаем до последнего закрытого </offer>
    text = xml.decode("utf-8", errors="ignore")
    end = text.rfind("</offer>")
    if end != -1:
        text = text[: end + len("</offer>")] + "</offers></shop></yml_catalog>"
    return text.encode("utf-8")


async def import_one(url: str) -> tuple[str, str, int, int]:
    src, feed_default = feed_meta(url)
    xml = _clean_xml(await asyncio.to_thread(fetch, url))
    seen: set[str] = set()
    inserted = updated = 0
    async with session_scope() as session:
        existing = {
            r.external_id: r
            for r in (await session.scalars(select(Item).where(Item.source == src))).all()
        }
        for fi in parse_feed(xml):
            if not fi.photo_url or fi.external_id in seen:
                continue
            seen.add(fi.external_id)
            # пол товара, а если не определён - дефолт бренда
            gender = fi.gender if fi.gender != "unisex" else (feed_default or "unisex")
            row = existing.get(fi.external_id)
            if row is None:
                session.add(Item(
                    source=src, external_id=fi.external_id, title=fi.title,
                    category=fi.category, gender=gender, color=fi.color, price=fi.price,
                    old_price=fi.old_price, sizes=fi.sizes or None,
                    photo_url=fi.photo_url, product_url=fi.product_url,
                    affiliate_url=fi.affiliate_url, in_stock=True,
                ))
                inserted += 1
            else:
                row.price, row.old_price, row.photo_url = fi.price, fi.old_price, fi.photo_url
                row.affiliate_url, row.product_url, row.color = (
                    fi.affiliate_url, fi.product_url, fi.color
                )
                row.gender, row.in_stock = gender, True
                updated += 1
        stale = [eid for eid in existing if eid not in seen]
        if stale:
            await session.execute(
                update(Item).where(Item.source == src, Item.external_id.in_(stale))
                .values(in_stock=False)
            )
        await session.commit()
    return src, src, inserted, updated


async def main() -> None:
    urls = [u.strip() for u in FEEDS_FILE.read_text().splitlines() if u.strip()]
    print(f"фидов: {len(urls)}")
    total = 0
    for url in urls:
        try:
            _, src, ins, upd = await import_one(url)
            total += ins + upd
            print(f"[{src}] +{ins} новых, ~{upd} обновлено")
        except Exception as e:  # один битый фид не рушит остальные
            print(f"[fail] {url[-40:]}: {type(e).__name__} {e}")
    print(f"итого товаров в работе: {total}")


if __name__ == "__main__":
    asyncio.run(main())
