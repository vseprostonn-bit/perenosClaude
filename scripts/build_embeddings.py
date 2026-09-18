"""Ночная обработка каталога: фото-эмбеддинги вещей (CLIP ViT-B/32, локально).

Память-бережная сборка. Прошлая версия держала в RAM ВЕСЬ индекс списком и на
каждом чекпоинте пересобирала его в новый массив - на 100k+ векторов процесс пух
и упирался в RAM+swap (инцидент 07-08.09). Теперь:
  - существующий индекс в память НЕ грузим, берём только его id (чтобы пропустить);
  - новые векторы копим отдельно в data/emb/_new_*.npy (возобновляемо);
  - в самом конце один раз мерджим существующий + новые -> data/emb/{vectors,ids}.npy.

Тяжёлые зависимости (torch, sentence-transformers) в requirements.txt бота НЕ входят.

Запуск (сервер, в фоне, низкий приоритет чтобы не мешать живому боту):
  cd ~/obraz-app && nice -n 15 ionice -c3 nohup .venv/bin/python \\
    -m scripts.build_embeddings > emb.log 2>&1 &

Страховка: если запас RAM+swap < 600 МБ - сохраняемся и выходим (возобновляемо),
прод не роняем.
"""

import asyncio
import io
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image
from sqlalchemy import select

from app.db import session_scope
from app.models import Item

EMB_DIR = Path(__file__).resolve().parent.parent / "data" / "emb"
VEC_FILE = EMB_DIR / "vectors.npy"
IDS_FILE = EMB_DIR / "ids.npy"
NEW_VEC = EMB_DIR / "_new_vectors.npy"  # только новые векторы этой сессии
NEW_IDS = EMB_DIR / "_new_ids.npy"
CHUNK = 64
DIM = 512
MODEL_NAME = "clip-ViT-B-32"


def _mem_headroom_mb() -> int:
    """RAM (MemAvailable) + свободный swap, в МБ. Страховка от настоящего OOM."""
    avail = swapfree = -1
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) // 1024
                elif line.startswith("SwapFree:"):
                    swapfree = int(line.split()[1]) // 1024
    except OSError:
        return 99999
    if avail < 0:
        return 99999
    return avail + max(0, swapfree)


def _download(url: str) -> Image.Image | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "obraz/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return Image.open(io.BytesIO(resp.read())).convert("RGB")
    except Exception:
        return None


def _existing_ids() -> set[int]:
    """Только id уже посчитанных вещей - без загрузки векторов в память."""
    if IDS_FILE.exists():
        return {int(x) for x in np.load(IDS_FILE).tolist()}
    return set()


def _load_new() -> tuple[list[int], list[np.ndarray]]:
    """Новые векторы прошлой прерванной сессии - для возобновления."""
    if NEW_IDS.exists() and NEW_VEC.exists():
        return np.load(NEW_IDS).tolist(), list(np.load(NEW_VEC))
    return [], []


def _save_new(ids: list[int], vecs: list[np.ndarray]) -> None:
    arr = np.array(vecs, dtype=np.float32) if vecs else np.zeros((0, DIM), np.float32)
    np.save(NEW_VEC, arr)
    np.save(NEW_IDS, np.array(ids, dtype=np.int64))


def _merge() -> int:
    """Существующий индекс + новые -> итоговые файлы. Разовый пик в самом конце."""
    ex_ids = np.load(IDS_FILE) if IDS_FILE.exists() else np.zeros((0,), np.int64)
    ex_vec = np.load(VEC_FILE) if VEC_FILE.exists() else np.zeros((0, DIM), np.float32)
    nw_ids = np.load(NEW_IDS)
    nw_vec = np.load(NEW_VEC)
    all_ids = np.concatenate([ex_ids.astype(np.int64), nw_ids.astype(np.int64)])
    all_vec = np.concatenate([ex_vec.astype(np.float32), nw_vec.astype(np.float32)])
    np.save(VEC_FILE, all_vec)
    np.save(IDS_FILE, all_ids)
    NEW_VEC.unlink(missing_ok=True)
    NEW_IDS.unlink(missing_ok=True)
    return len(all_ids)


async def _catalog() -> list[tuple[int, str]]:
    async with session_scope() as session:
        rows = (
            await session.scalars(
                select(Item).where(Item.in_stock.is_(True), Item.photo_url.is_not(None))
            )
        ).all()
        return [(it.id, it.photo_url) for it in rows if it.photo_url]


def main() -> None:
    EMB_DIR.mkdir(parents=True, exist_ok=True)
    from sentence_transformers import SentenceTransformer

    catalog = asyncio.run(_catalog())
    done = _existing_ids()
    new_ids, new_vecs = _load_new()
    done |= set(new_ids)
    todo = [(iid, url) for iid, url in catalog if iid not in done]
    print(f"каталог: {len(catalog)}, готово: {len(done)}, к обработке: {len(todo)}", flush=True)
    if not todo:
        if NEW_IDS.exists():
            print(f"мердж {len(new_ids)} новых в индекс...", flush=True)
            print(f"готово: индекс {_merge()}", flush=True)
        else:
            print("нечего считать", flush=True)
        return

    model = SentenceTransformer(MODEL_NAME)
    pool = ThreadPoolExecutor(max_workers=6)
    processed = 0
    for i in range(0, len(todo), CHUNK):
        head = _mem_headroom_mb()
        if head < 600:  # RAM+swap почти исчерпаны - сохраняемся и выходим до OOM
            _save_new(new_ids, new_vecs)
            print(f"!!! запас RAM+swap {head}МБ<600, новых {len(new_ids)}, выход", flush=True)
            return
        batch = todo[i : i + CHUNK]
        images = list(pool.map(lambda p: _download(p[1]), batch))
        good = [(iid, img) for (iid, _), img in zip(batch, images, strict=True) if img is not None]
        if good:
            embs = model.encode(
                [img for _, img in good], batch_size=32, normalize_embeddings=True
            )
            for (iid, _), emb in zip(good, embs, strict=True):
                new_ids.append(iid)
                new_vecs.append(np.asarray(emb, dtype=np.float32))
        processed += len(batch)
        if i % (CHUNK * 10) == 0:
            _save_new(new_ids, new_vecs)
            print(f"  {processed}/{len(todo)} (новых {len(new_ids)})", flush=True)

    _save_new(new_ids, new_vecs)
    print(f"мердж {len(new_ids)} новых в индекс...", flush=True)
    print(f"готово: индекс {_merge()}", flush=True)


if __name__ == "__main__":
    main()
