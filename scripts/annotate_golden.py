"""Помощник разметки контрольного набора.

Руками размечать 150 фото - долго и скучно, поэтому скучное делает скрипт:
разбирает фото, находит кандидатов по каждой вещи и раскладывает их в json
с картинками. Человеку остаётся посмотреть на превью и перенести id в
нужный список. Это единственная работа, которую нельзя автоматизировать:
что считать «той самой вещью», решает человек.

  add <фото>   положить фото в набор, разобрать, подсказать кандидатов
  enrich       дозаполнить разбор и кандидатов у фото, добавленных без каталога
  resuggest    пересобрать кандидатов из сохранённого разбора, без запроса к vision
  html         собрать превью: фото лука и кандидаты картинками
  check        проверить набор: битые id, пустые слоты, статистика

Набор можно собирать в два захода. Сначала - фото, без ИИ и каталога:
`add <фото> --no-scan` работает на любой машине. Когда каталог доступен -
`enrich` проходит по таким записям, разбирает фото и подставляет кандидатов.

Запуск (из корня проекта):
  .venv/bin/python -m scripts.annotate_golden add ~/Downloads/look.jpg
  .venv/bin/python -m scripts.annotate_golden resuggest
  .venv/bin/python -m scripts.annotate_golden html
  .venv/bin/python -m scripts.annotate_golden check

Методология - docs/metodologiya-matchinga-2026-09-03.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.golden_format import (
    candidate_key,
    candidates_for_items,
    duplicate_slot_indices,
    looks_for_items,
)

if TYPE_CHECKING:  # только для подсказок типов
    from app.services.lookscan import LookItem

GOLDEN = Path(__file__).resolve().parent.parent / "eval" / "golden"
PREVIEW = GOLDEN / "preview.html"
SLOTS = ("top", "bottom", "dress", "outerwear", "shoes", "bag", "accessory")
SUGGEST_PER_SLOT = 8


def _next_id() -> str:
    used = [int(p.stem) for p in GOLDEN.glob("*.json") if p.stem.isdigit()]
    return f"{(max(used) + 1) if used else 1:03d}"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


PASSPORT_FIELDS = ("type", "silhouette", "length", "sleeve", "neckline", "fit", "pattern")


def _look_dict(item: LookItem) -> dict[str, Any]:
    return {"slot": item.category, "category": item.category, "name": item.name,
            "color": item.color, "search_query": item.search_query,
            **{f: getattr(item, f) for f in PASSPORT_FIELDS}}


def _look_item(raw: dict[str, Any]) -> LookItem:
    """Вещь из кэша разбора - с паспортом, как её видел поиск в момент enrich."""
    from app.services.lookscan import LookItem

    return LookItem(
        category=raw.get("category") or raw.get("slot") or "",
        name=raw.get("name") or "",
        color=raw.get("color") or "",
        search_query=raw.get("search_query") or raw.get("name") or "",
        **{f: raw.get(f) for f in PASSPORT_FIELDS},
    )


async def _suggest(look_items: list[LookItem], gender: str) -> list[list[dict[str, Any]]]:
    """Кандидаты по каждой вещи, по её номеру - то, из чего человек выбирает правильные.

    Список по номеру, а не словарь по слоту: у двух аксессуаров на одном фото
    слот один, и раньше второй затирал кандидатов первого.
    """
    from app.db import session_scope
    from app.services.catalog import search_scored

    out: list[list[dict[str, Any]]] = []
    async with session_scope() as session:
        for look in look_items:
            scored = await search_scored(session, look, gender=gender, limit=SUGGEST_PER_SLOT)
            out.append([
                {
                    "id": m.item.id,
                    "title": m.item.title,
                    "store": m.item.source,
                    "color": m.item.color,
                    "price": m.item.price,
                    "score": m.score,
                    "photo_url": m.item.photo_url,
                }
                for m in scored
            ])
    return out


async def cmd_add(photo: Path, gender: str, scan: bool) -> int:
    if not photo.exists():
        print(f"нет файла: {photo}")
        return 1
    GOLDEN.mkdir(parents=True, exist_ok=True)
    number = _next_id()
    target = GOLDEN / f"{number}{photo.suffix.lower()}"
    shutil.copy(photo, target)

    look_items: list[LookItem] = []
    vibe = ""
    if scan:
        from app.services.lookscan import analyze_look

        analysis = await analyze_look(target.read_bytes())
        if analysis is None or not analysis.is_outfit:
            print("разбор не удался - создаю пустой скелет, слоты впиши руками")
        else:
            look_items = analysis.items
            vibe = analysis.vibe
            gender = analysis.gender if analysis.gender in ("women", "men") else gender

    data: dict[str, Any] = {
        "gender": gender,
        "note": "",
        "vibe": vibe,
        "items": [{"slot": i.category, "exact": [], "acceptable": []} for i in look_items]
        or [{"slot": "top", "exact": [], "acceptable": []}],
        "look": [_look_dict(i) for i in look_items],
    }
    if look_items:
        data["suggestions_by_item"] = await _suggest(look_items, data["gender"])

    _save(GOLDEN / f"{number}.json", data)
    print(f"добавлено: {target.name} и {number}.json")
    print(f"вещей в разборе: {len(look_items)}")
    print("дальше: собери превью (html) и перенеси id из suggestions в exact/acceptable")
    return 0


async def cmd_enrich(only: str | None = None) -> int:
    """Дозаполняет записи, добавленные без каталога: разбор плюс кандидаты.

    Нужна, когда фото собирали на ноутбуке (`add --no-scan`), а каталог живёт
    на сервере: сама разметка руками от этого не зависит и не теряется.
    """
    from app.services.lookscan import analyze_look

    done = 0
    for meta_path in sorted(GOLDEN.glob("*.json")):
        if only and only not in meta_path.stem:
            continue
        data = _load(meta_path)
        if data.get("look"):
            continue  # уже обогащено, повторно ИИ не дёргаем
        photo = next((p for p in GOLDEN.glob(f"{meta_path.stem}.*") if p.suffix != ".json"), None)
        if photo is None:
            print(f"  {meta_path.stem}: нет файла фото, пропускаю")
            continue

        analysis = await analyze_look(photo.read_bytes())
        if analysis is None or not analysis.is_outfit:
            print(f"  {meta_path.stem}: разбор не удался")
            continue

        gender = analysis.gender
        if gender not in ("women", "men"):
            gender = data.get("gender", "women")
        data["gender"] = gender
        data["vibe"] = analysis.vibe
        data["look"] = [_look_dict(i) for i in analysis.items]
        # Слоты, которые уже размечены руками, сохраняем: разметка дороже разбора.
        # k-я размеченная вещь слота переходит к k-й вещи этого слота в разборе.
        marked: dict[str, list[dict[str, Any]]] = {}
        for i in data.get("items", []):
            if i.get("verdict") or i.get("exact") or i.get("acceptable"):
                marked.setdefault(i["slot"], []).append(i)
        items = []
        for i in analysis.items:
            pool = marked.get(i.category) or []
            empty = {"slot": i.category, "exact": [], "acceptable": []}
            items.append(pool.pop(0) if pool else empty)
        data["items"] = items or data.get("items", [])
        data["suggestions_by_item"] = await _suggest(analysis.items, gender)
        data.pop("suggestions", None)

        _save(meta_path, data)
        done += 1
        print(f"  {meta_path.stem}: вещей {len(analysis.items)}, кандидатов подобрано")

    print(f"обогащено записей: {done}")
    return 0


async def cmd_resuggest(only: str | None = None) -> int:
    """Пересобрать кандидатов из сохранённого разбора. GigaChat не вызывается.

    Нужна после правок поиска: дубли размеров схлопнулись, и в восьмёрке теперь
    восемь разных вещей, а двойники-аксессуары получают каждый свой список.
    Разметка не теряется: размеченные вещи остаются в списке, даже если новый
    поиск их не поднял. Что стоит перепроверить, помечается полем recheck -
    страница разметки показывает эти вещи отдельно:
      duplicate       - на фото два одинаковых слота, кандидаты были перепутаны;
      new_candidates  - стояло «нет в каталоге», а среди кандидатов появились новые вещи.
    """
    photos = rechecks = duplicates = 0
    for meta_path in sorted(GOLDEN.glob("[0-9][0-9][0-9].json")):
        if only and only not in meta_path.stem:
            continue
        data = _load(meta_path)
        items = data.get("items") or []
        looks = looks_for_items(data)
        if not items or not any(looks):
            continue
        old_lists, mixed = candidates_for_items(data)
        dup = duplicate_slot_indices(data) if mixed else set()

        present = [(idx, raw) for idx, raw in enumerate(looks) if raw]
        fresh = await _suggest([_look_item(raw) for _, raw in present], data.get("gender", "women"))
        new_lists: list[list[dict[str, Any]]] = [[] for _ in items]
        for (idx, _), cands in zip(present, fresh, strict=True):
            new_lists[idx] = cands

        for idx, item in enumerate(items):
            cands = new_lists[idx]
            labeled = set(item.get("exact") or []) | set(item.get("acceptable") or [])
            # Размеченные вещи оставляем видимыми: иначе страница показывает
            # «размечено», а отмеченной карточки нигде нет.
            have_ids = {c["id"] for c in cands}
            have_keys = {candidate_key(c) for c in cands}
            kept = [c for c in old_lists[idx] if c["id"] in labeled
                    and c["id"] not in have_ids and candidate_key(c) not in have_keys]
            new_lists[idx] = kept + cands

            item.pop("recheck", None)
            if not item.get("verdict"):
                continue  # не размечено - и так будет размечено с новыми кандидатами
            if idx in dup:
                item["recheck"] = "duplicate"
                duplicates += 1
            elif item["verdict"] == "not_in_catalog":
                old_keys = {candidate_key(c) for c in old_lists[idx]}
                if {candidate_key(c) for c in cands} - old_keys:
                    item["recheck"] = "new_candidates"
            if item.get("recheck"):
                rechecks += 1

        data["suggestions_by_item"] = new_lists
        data.pop("suggestions", None)
        _save(meta_path, data)
        photos += 1

    print(f"кандидаты пересобраны: фото {photos}")
    print(f"на перепроверку: {rechecks} вещей, из них двойников-слотов {duplicates}")
    print("дальше: python -m scripts.label_golden build, страница покажет, что проверить")
    return 0


def cmd_html() -> int:
    """Превью: фото лука рядом с кандидатами. Глазами выбирать быстрее всего."""
    cards = []
    for meta_path in sorted(GOLDEN.glob("*.json")):
        data = _load(meta_path)
        photo = next((p for p in GOLDEN.glob(f"{meta_path.stem}.*") if p.suffix != ".json"), None)
        blocks = []
        candidate_lists, _ = candidates_for_items(data)
        for idx, item in enumerate(data.get("items", [])):
            slot = item["slot"]
            marked = set(item.get("exact", [])) | set(item.get("acceptable", []))
            suggestions = candidate_lists[idx]
            thumbs = "".join(
                f'<figure class="{"on" if s["id"] in marked else ""}">'
                f'<img src="{escape(str(s.get("photo_url") or ""))}" loading="lazy">'
                f'<figcaption><b>{s["id"]}</b> {escape(s["title"][:38])}<br>'
                f'{s["price"]} р · {escape(str(s.get("color") or "-"))} · '
                f'скор {s["score"]}</figcaption></figure>'
                for s in suggestions
            )
            blocks.append(
                f'<div class="slot"><h3>{escape(slot)} '
                f'<small>размечено: {len(marked) or "нет"}</small></h3>'
                f'<div class="thumbs">{thumbs or "<i>кандидатов нет</i>"}</div></div>'
            )
        cards.append(
            f'<section><h2>{meta_path.stem}</h2>'
            f'<div class="row"><img class="look" src="{escape(photo.name if photo else "")}">'
            f'<div class="slots">{"".join(blocks)}</div></div></section>'
        )

    html = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<title>Разметка контрольного набора</title><style>
body{{font-family:system-ui,sans-serif;margin:24px;background:#FFF8F6;color:#1A1A1E}}
h1{{font-size:22px}} section{{background:#fff;border-radius:16px;padding:16px;margin-bottom:20px}}
.row{{display:flex;gap:20px;align-items:flex-start}}
.look{{width:260px;border-radius:12px}}
.slots{{flex:1}} .slot{{margin-bottom:14px}}
.slot h3{{font-size:15px;margin:0 0 8px}} .slot small{{color:#9A8F8F;font-weight:400}}
.thumbs{{display:flex;gap:10px;overflow-x:auto;padding-bottom:6px}}
figure{{margin:0;width:120px;flex:0 0 auto;border:2px solid transparent;
  border-radius:10px;padding:4px}}
figure.on{{border-color:#FF4D6A;background:#FFF0F2}}
figure img{{width:112px;height:150px;object-fit:cover;border-radius:8px;background:#eee}}
figcaption{{font-size:11px;line-height:1.3;margin-top:4px;color:#555}}
</style></head><body>
<h1>Разметка контрольного набора</h1>
<p>Смотри на кандидатов, выписывай id, переноси их в <code>exact</code> или
<code>acceptable</code> в соответствующем json. Розовой рамкой отмечено то,
что уже размечено.</p>
{"".join(cards) or "<p>Набор пуст.</p>"}
</body></html>"""
    PREVIEW.write_text(html, encoding="utf-8")
    print(f"превью собрано: {PREVIEW}")
    return 0


async def cmd_check() -> int:
    """Проверка набора: битые id, неизвестные слоты, готовность к замеру."""
    photos = marked_slots = total_slots = empty_marks = 0
    problems: list[str] = []
    all_ids: set[int] = set()

    for meta_path in sorted(GOLDEN.glob("*.json")):
        photos += 1
        data = _load(meta_path)
        if not any(GOLDEN.glob(f"{meta_path.stem}.[jp][pn]*")):
            problems.append(f"{meta_path.stem}: нет файла фото")
        for item in data.get("items", []):
            total_slots += 1
            if item["slot"] not in SLOTS:
                problems.append(f"{meta_path.stem}: неизвестный слот {item['slot']}")
            ids = list(item.get("exact", [])) + list(item.get("acceptable", []))
            all_ids.update(ids)
            if ids:
                marked_slots += 1
            else:
                empty_marks += 1
        if not data.get("look"):
            problems.append(f"{meta_path.stem}: нет кэша разбора, прогони eval с --stage full")

    if all_ids:
        from sqlalchemy import select

        from app.db import session_scope
        from app.models import Item

        async with session_scope() as session:
            found = set(
                (await session.scalars(select(Item.id).where(Item.id.in_(all_ids)))).all()
            )
        for missing in sorted(all_ids - found):
            problems.append(f"id {missing} размечен, но такой вещи в каталоге нет")

    print(f"фото в наборе:            {photos}")
    print(f"слотов всего:             {total_slots}")
    print(f"слотов с разметкой:       {marked_slots}")
    print(f"слотов помечено «нет в каталоге»: {empty_marks}")
    if problems:
        print("\nПроблемы:")
        for line in problems[:30]:
            print(f"  {line}")
    else:
        print("\nПроблем нет.")
    if photos < 100:
        print(f"\nДля осмысленных метрик нужно 100-150 фото, сейчас {photos}.")
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Помощник разметки контрольного набора")
    sub = ap.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add", help="добавить фото в набор и подсказать кандидатов")
    add.add_argument("photo", type=Path)
    add.add_argument("--gender", default="women", choices=("women", "men"))
    add.add_argument("--no-scan", action="store_true", help="без обращения к vision")

    enrich_p = sub.add_parser("enrich", help="дозаполнить разбор и кандидатов")
    enrich_p.add_argument("--only", help="только фото, чей id содержит эту строку")

    resuggest_p = sub.add_parser("resuggest", help="пересобрать кандидатов без vision")
    resuggest_p.add_argument("--only", help="только фото, чей id содержит эту строку")

    sub.add_parser("html", help="собрать превью для разметки глазами")
    sub.add_parser("check", help="проверить набор")

    args = ap.parse_args()
    if args.cmd == "add":
        return asyncio.run(cmd_add(args.photo, args.gender, not args.no_scan))
    if args.cmd == "enrich":
        return asyncio.run(cmd_enrich(args.only))
    if args.cmd == "resuggest":
        return asyncio.run(cmd_resuggest(args.only))
    if args.cmd == "html":
        return cmd_html()
    return asyncio.run(cmd_check())


if __name__ == "__main__":
    raise SystemExit(main())
