"""Разведчик товарного фида перед добавлением в каталог.

Показывает название магазина, число товаров, распределение по полу и категориям
и пару примеров - чтобы задать источник и дефолтный пол в FEED_META
(scripts/import_feeds.py) до импорта. Пол по умолчанию важен: без него мужское
или детское из фида с меткой unisex утечёт в женские выдачи.

Читает URL из data/admitad_feeds.txt (в git не коммитим), фильтрует по feed_id:

    cd ~/obraz-app && .venv/bin/python -m scripts.peek_feed 21692
"""

import re
import sys
from collections import Counter
from pathlib import Path

from app.services.feed_import import parse_feed
from scripts.import_feeds import _clean_xml, fetch

FEEDS = Path(__file__).resolve().parent.parent / "data" / "admitad_feeds.txt"
wanted = set(sys.argv[1:])

for url in (u.strip() for u in FEEDS.read_text().splitlines() if u.strip()):
    m = re.search(r"feed_id=(\d+)", url)
    fid = m.group(1) if m else "?"
    if wanted and fid not in wanted:
        continue
    try:
        xml = _clean_xml(fetch(url))
    except Exception as e:  # noqa: BLE001
        print(f"feed {fid}: fetch fail {type(e).__name__} {e}")
        continue
    text = xml.decode("utf-8", errors="ignore")
    shop = re.search(r"<shop>.*?<name>(.*?)</name>", text, re.S)
    items = list(parse_feed(xml))
    genders = Counter(fi.gender for fi in items)
    cats = Counter(fi.category for fi in items)
    print(f"feed {fid}: '{shop.group(1) if shop else '?'}', товаров {len(items)}")
    print(f"    пол: {dict(genders)}")
    print(f"    категории: {dict(cats.most_common(6))}")
    for fi in items[:2]:
        print(f"    пример: {fi.category} | {fi.gender} | {fi.title[:45]}")
