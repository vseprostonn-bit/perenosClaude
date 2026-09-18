"""Линейка качества матчинга: прогон контрольного набора и метрики.

Без этого скрипта любое «стало лучше» - ощущение. С ним - строка в
docs/matching-log.md, которую можно сравнить со вчерашней.

Набор лежит в eval/golden/: <id>.jpg плюс <id>.json с разметкой.
Формат разметки - eval/golden/README.md.

Три режима:

  match (по умолчанию) - берёт готовый разбор из поля "look" в json и меряет
  ТОЛЬКО поиск по каталогу. Не тратит запросы к vision, гоняется хоть каждые
  пять минут. Именно им меряем правки в catalog.py.

  full - гоняет фото через analyze_look и меряет всю цепочку вместе с
  распознаванием. Тратит лимиты GigaChat, поэтому запускается редко.
  Разбор кэшируется обратно в json, дальше можно работать в режиме match.

  offline - без базы и сервера: порядок кандидатов, сохранённых в наборе.
  Точка ориентировочная (12.09 реальный поиск дал top-1 28.6% против офлайновых
  37%), зато снимается на любой машине сразу после разметки.

Попадание засчитывается по товару, а не по id: фиды заводят позицию на каждый
размер, и размеченные кроссовки 38-го размера и найденные 39-го - одна вещь.

Запуск:
  .venv/bin/python -m scripts.eval_matching
  .venv/bin/python -m scripts.eval_matching --stage full
  uv run --with-requirements requirements.txt python -m scripts.eval_matching --stage offline
  .venv/bin/python -m scripts.eval_matching --note "гибридный реранк"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.golden_format import candidate_key, candidates_for_items, looks_for_items

if TYPE_CHECKING:
    from app.services.lookscan import LookItem

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "eval" / "golden"
LAST_RUN = Path(__file__).resolve().parent.parent / "eval" / "last-run.json"
TOP_N = 3


@dataclass
class SlotCase:
    """Один слот одного фото: чего ждём и что вернул поиск."""

    photo: str
    slot: str
    look: LookItem
    gender: str | None
    exact: set[int]
    acceptable: set[int]
    candidates: list[dict[str, Any]]
    candidates_mixed: bool = False

    @property
    def right(self) -> set[int]:
        return self.exact | self.acceptable


def load_cases(only: str | None = None) -> list[SlotCase]:
    from app.services.lookscan import LookItem

    cases: list[SlotCase] = []
    for meta_path in sorted(GOLDEN_DIR.glob("[0-9][0-9][0-9].json")):
        if only and only not in meta_path.stem:
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        gender = meta.get("gender")
        # По номеру вещи: у двух аксессуаров на фото раньше был один разбор на двоих.
        looks = looks_for_items(meta)
        candidate_lists, mixed = candidates_for_items(meta)
        slot_counts = Counter(i["slot"] for i in meta.get("items", []))
        dup_slots = {slot for slot, n in slot_counts.items() if n > 1}
        for idx, item in enumerate(meta.get("items", [])):
            slot = item["slot"]
            verdict = item.get("verdict")
            exact, acceptable = item.get("exact", []), item.get("acceptable", [])
            # «Этой вещи на фото нет» и «бот определил неверно» - ошибки
            # распознавания, а не поиска: они меряются отдельно, в точность
            # подбора не идут - искали не ту вещь.
            if verdict in ("absent", "wrong"):
                continue
            # Пустые списки без вердикта - слот ещё не размечен. Раньше он молча
            # засчитывался как «в каталоге нет» и завышал долю честных отказов.
            if not verdict and not exact and not acceptable:
                continue
            raw = looks[idx]
            if not raw:
                continue  # нет кэшированного разбора - слот считается в режиме full
            passport = {f: raw.get(f) for f in
                        ("type", "silhouette", "length", "sleeve", "neckline", "fit", "pattern")}
            cases.append(
                SlotCase(
                    photo=meta_path.stem,
                    slot=slot,
                    look=LookItem(
                        category=raw.get("category", slot),
                        name=raw.get("name", ""),
                        color=raw.get("color", ""),
                        search_query=raw.get("search_query", raw.get("name", "")),
                        **passport,
                    ),
                    gender=gender,
                    exact=set(exact),
                    acceptable=set(acceptable),
                    candidates=candidate_lists[idx],
                    candidates_mixed=mixed and slot in dup_slots,
                )
            )
    return cases


def review_stats() -> dict:
    """Что показала разметка сама по себе, без прогона поиска.

    Доля «этого нет на фото» - как часто распознавание выдумывает вещи. Её не
    видно в top-1: выдуманный слот просто выпадает. С 15.09 рядом ещё две меры
    распознавания: «назвал неверно» и «не увидел вовсе» - по фото, где Саша
    отметил, всё ли бот увидел.
    """
    total = reviewed = absent = not_in_catalog = wrong = 0
    photos_checked = photos_missed = 0
    missed_by_slot: Counter[str] = Counter()
    wrong_by_slot: Counter[str] = Counter()
    for meta_path in sorted(GOLDEN_DIR.glob("[0-9][0-9][0-9].json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        for item in meta.get("items", []):
            total += 1
            verdict = item.get("verdict")
            if verdict or item.get("exact") or item.get("acceptable"):
                reviewed += 1
            if verdict == "absent":
                absent += 1
            elif verdict == "not_in_catalog":
                not_in_catalog += 1
            elif verdict == "wrong":
                wrong += 1
                wrong_by_slot[item["slot"]] += 1
        missed = meta.get("missed") or {}
        if missed.get("reviewed"):
            photos_checked += 1
            if missed.get("slots"):
                photos_missed += 1
                missed_by_slot.update(missed["slots"])
    pct = lambda part, whole: round(100 * part / whole, 1) if whole else 0.0  # noqa: E731
    return {
        "слотов размечено": f"{reviewed} из {total}",
        "выдуманных вещей (нет на фото), %": pct(absent, reviewed),
        "вещь названа неверно, %": pct(wrong, reviewed),
        "вещей нет в каталоге, %": pct(not_in_catalog, reviewed),
        "фото проверено на пропуски": photos_checked,
        "фото, где бот не увидел вещь, %": pct(photos_missed, photos_checked),
        "_не увидел по слотам": dict(missed_by_slot.most_common()),
        "_назвал неверно по слотам": dict(wrong_by_slot.most_common()),
    }


def recognition_errors(limit: int = 30) -> list[str]:
    """Строки «бот увидел -> на самом деле» - сырьё для правки промпта."""
    lines: list[str] = []
    for meta_path in sorted(GOLDEN_DIR.glob("[0-9][0-9][0-9].json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        looks = looks_for_items(meta)
        for idx, item in enumerate(meta.get("items", [])):
            if item.get("verdict") != "wrong":
                continue
            raw = looks[idx] or {}
            seen = " ".join(v for v in (raw.get("name"), raw.get("color")) if v) or "-"
            lines.append(f"{meta_path.stem} {item['slot']}: {seen} -> {item.get('actual') or '?'}")
        missed = meta.get("missed") or {}
        if missed.get("slots"):
            note = f" ({missed['note']})" if missed.get("note") else ""
            lines.append(f"{meta_path.stem} не увидел: {', '.join(missed['slots'])}{note}")
    return lines[:limit]


def run_offline(cases: list[SlotCase]) -> dict:
    """Метрики по порядку сохранённых кандидатов, без базы.

    Дубли размеров схлопываются по фото и названию карточки - так, как их
    теперь схлопывает поиск. Слоты-двойники со старыми перепутанными
    кандидатами пропускаются: мерить на них нечего.
    """
    ranks: list[int] = []
    empty_expected = skipped = 0
    per_slot: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for case in cases:
        if case.candidates_mixed:
            skipped += 1
            continue
        per_slot[case.slot][1] += 1
        if not case.right:
            empty_expected += 1
            continue
        right_keys = {candidate_key(c) for c in case.candidates if c["id"] in case.right}
        unique: list[tuple[str, str]] = []
        for c in case.candidates:
            if candidate_key(c) not in unique:
                unique.append(candidate_key(c))
        rank = next((n for n, key in enumerate(unique, 1) if key in right_keys), 0)
        ranks.append(rank)
        per_slot[case.slot][0] += 1
    scored = len(ranks)
    pct = lambda part, whole: round(100 * part / whole, 1) if whole else 0.0  # noqa: E731
    return {
        **review_stats(),
        "слотов всего": len(cases) - skipped,
        "слотов-двойников пропущено": skipped,
        "top-1 hit, %": pct(sum(1 for r in ranks if r == 1), scored),
        "top-3 hit, %": pct(sum(1 for r in ranks if 1 <= r <= 3), scored),
        "MRR": round(sum(1 / r for r in ranks if r) / scored, 3) if scored else 0.0,
        "подходящей нет среди кандидатов, %": pct(empty_expected, scored + empty_expected),
        "_нет среди кандидатов по слотам, %": {
            slot: pct(total - found, total) for slot, (found, total) in sorted(per_slot.items())
        },
        "_промахи": [],
    }


async def run_matching(cases: list[SlotCase]) -> dict:
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import Item
    from app.services.catalog import product_key, search_catalog

    hits1 = hits3 = exact1 = 0
    empty_expected = empty_ok = 0
    rr_total = 0.0
    times: list[float] = []
    misses: list[tuple[str, str]] = []

    async with session_scope() as session:
        labeled = set().union(*(c.right for c in cases)) if cases else set()
        rows = (await session.scalars(select(Item).where(Item.id.in_(labeled)))).all()
        key_of = {item.id: product_key(item) for item in rows}

        for case in cases:
            started = time.perf_counter()
            found = await search_catalog(session, case.look, case.gender, limit=TOP_N)
            times.append(time.perf_counter() - started)
            keys = [product_key(it) for it in found]

            if not case.right:
                # В каталоге такого нет. Правильное поведение - пустой ответ.
                empty_expected += 1
                if not keys:
                    empty_ok += 1
                continue

            # По товару: размеченный размер и найденный другой размер - одна вещь
            right = {key_of[i] for i in case.right if i in key_of}
            exact = {key_of[i] for i in case.exact if i in key_of}
            if keys[:1] and keys[0] in right:
                hits1 += 1
                if keys[0] in exact:
                    exact1 += 1
            if any(k in right for k in keys):
                hits3 += 1
            else:
                misses.append((case.photo, case.slot))

            rank = next((n for n, k in enumerate(keys, 1) if k in right), 0)
            rr_total += 1 / rank if rank else 0.0

    scored = len(cases) - empty_expected
    pct = lambda part, whole: round(100 * part / whole, 1) if whole else 0.0  # noqa: E731
    return {
        **review_stats(),
        "слотов всего": len(cases),
        "слотов с ожидаемым ответом": scored,
        "top-1 hit, %": pct(hits1, scored),
        "top-3 hit, %": pct(hits3, scored),
        "точное попадание в top-1, %": pct(exact1, scored),
        "MRR": round(rr_total / scored, 3) if scored else 0.0,
        "честный пустой ответ, %": pct(empty_ok, empty_expected),
        "среднее время слота, с": round(sum(times) / len(times), 3) if times else 0.0,
        "_промахи": misses[:15],
    }


async def refresh_cache(only: str | None = None) -> int:
    """Режим full: гоняет фото через vision и кэширует разбор обратно в json."""
    from app.services.lookscan import analyze_look

    updated = 0
    for meta_path in sorted(GOLDEN_DIR.glob("*.json")):
        if only and only not in meta_path.stem:
            continue
        photo = next((p for p in (meta_path.with_suffix(ext) for ext in (".jpg", ".jpeg", ".png"))
                      if p.exists()), None)
        if not photo:
            print(f"  {meta_path.stem}: нет файла фото, пропускаю")
            continue
        analysis = await analyze_look(photo.read_bytes())
        if analysis is None or not analysis.is_outfit:
            print(f"  {meta_path.stem}: разбор не удался")
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        # С паспортом вещи: без него поиск в замере беднее, чем в продукте
        from scripts.annotate_golden import _look_dict

        meta["look"] = [_look_dict(i) for i in analysis.items]
        meta["vibe"] = analysis.vibe
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        updated += 1
        print(f"  {meta_path.stem}: разобрано вещей {len(analysis.items)}")
    return updated


def slot_coverage(only: str | None = None) -> dict:
    """Насколько разбор видит те слоты, которые размечены руками (с повторами)."""
    expected = detected = 0
    for meta_path in sorted(GOLDEN_DIR.glob("[0-9][0-9][0-9].json")):
        if only and only not in meta_path.stem:
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        want = Counter(i["slot"] for i in meta.get("items", []))
        have = Counter(i.get("slot") for i in meta.get("look", []))
        expected += sum(want.values())
        detected += sum((want & have).values())
    return {"слотов в наборе": expected,
            "слотов найдено разбором, %": round(100 * detected / expected, 1) if expected else 0.0}


def compare_with_last(result: dict) -> list[str]:
    if not LAST_RUN.exists():
        return []
    prev = json.loads(LAST_RUN.read_text(encoding="utf-8")).get("metrics", {})
    lines = []
    for key, value in result.items():
        if key.startswith("_") or not isinstance(value, (int, float)):
            continue
        old = prev.get(key)
        if isinstance(old, (int, float)) and old != value:
            delta = round(value - old, 3)
            lines.append(f"  {key}: {old} -> {value} ({'+' if delta > 0 else ''}{delta})")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description="Метрики матчинга по контрольному набору")
    ap.add_argument("--stage", choices=("match", "full", "offline"), default="match",
                    help="match - поиск по каталогу; full - ещё и разбор фото; "
                         "offline - порядок сохранённых кандидатов, без базы")
    ap.add_argument("--only", help="прогнать только фото, чей id содержит эту строку")
    ap.add_argument("--note", default="", help="комментарий: что именно поменяли")
    args = ap.parse_args()

    if not GOLDEN_DIR.exists() or not any(GOLDEN_DIR.glob("*.json")):
        print(f"Контрольного набора нет: {GOLDEN_DIR}")
        print("Как его собрать - eval/golden/README.md")
        return 1

    if args.stage == "full":
        print("Разбор фото через vision (тратит лимиты GigaChat):")
        updated = asyncio.run(refresh_cache(args.only))
        print(f"обновлено разборов: {updated}\n")

    coverage = slot_coverage(args.only)
    cases = load_cases(args.only)
    if not cases:
        print("Нет ни одного слота с кэшированным разбором.")
        print("Запусти один раз с --stage full, чтобы наполнить кэш.")
        return 1

    result = run_offline(cases) if args.stage == "offline" else asyncio.run(run_matching(cases))

    print("=" * 52)
    print("КАЧЕСТВО МАТЧИНГА" + (f" - {args.note}" if args.note else ""))
    print("=" * 52)
    for key, value in coverage.items():
        print(f"{key:38} {value}")
    for key, value in result.items():
        if not key.startswith("_"):
            print(f"{key:38} {value}")

    diff = compare_with_last(result)
    if diff:
        print("\nОтносительно прошлого прогона:")
        print("\n".join(diff))

    for key in ("_не увидел по слотам", "_назвал неверно по слотам",
                "_нет среди кандидатов по слотам, %"):
        if result.get(key):
            print(f"{key.lstrip('_'):38} {result[key]}")

    if result["_промахи"]:
        print("\nПромахи (фото / слот):")
        for photo, slot in result["_промахи"]:
            print(f"  {photo}  {slot}")

    errors = recognition_errors()
    if errors:
        print("\nОшибки распознавания (бот увидел -> на самом деле):")
        for line in errors:
            print(f"  {line}")

    LAST_RUN.parent.mkdir(parents=True, exist_ok=True)
    if args.stage == "offline":
        print("\nОфлайн-точка в last-run.json не пишется: её не с чем честно сравнивать.")
        return 0
    LAST_RUN.write_text(
        json.dumps({"note": args.note,
                    "metrics": {k: v for k, v in result.items() if not k.startswith("_")}},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\nРезультат сохранён в {LAST_RUN.name}, следующий прогон сравнится с ним.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
