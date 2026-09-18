"""Визуальный сигнал: близость фото вещи к фото карточек каталога.

Индекс считается отдельно и заранее - `scripts/build_embeddings.py` кладёт
`data/emb/vectors.npy` (N x D, нормализованные) и `data/emb/ids.npy`.
Здесь только чтение: загрузили один раз в память, дальше перемножение матриц.
На 42 тысячах векторов это доли миллисекунды, векторная база не нужна.

Модуль намеренно необязательный. Нет файлов индекса, не стоит numpy, не стоит
энкодер - всё продолжает работать без визуального сигнала, просто хуже
ранжирует. Матчинг не должен падать из-за отсутствия ночной обработки.

Методология - docs/metodologiya-matchinga-2026-09-03.md
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

EMB_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "emb"
VEC_FILE = EMB_DIR / "vectors.npy"
IDS_FILE = EMB_DIR / "ids.npy"

# Должна совпадать с моделью в scripts/build_embeddings.py, иначе векторы
# запроса и каталога будут из разных пространств и близость станет мусором.
MODEL_NAME = "clip-ViT-B-32"

_index: tuple[Any, dict[int, int]] | None = None
_index_tried = False
_encoder: Any = None
_encoder_tried = False


def _load_index() -> tuple[Any, dict[int, int]] | None:
    """(матрица векторов, id вещи -> строка матрицы). None, если индекса нет."""
    global _index, _index_tried
    if _index is not None or _index_tried:
        return _index
    _index_tried = True
    if not (VEC_FILE.exists() and IDS_FILE.exists()):
        log.info("индекс эмбеддингов не найден в %s - визуальный сигнал выключен", EMB_DIR)
        return None
    try:
        import numpy as np

        # mmap: матрица читается с диска через кэш страниц, а не копируется в
        # память каждого процесса. uvicorn и бот делят одну копию, и под
        # нехваткой памяти ядро может её вытеснить, а не убивать процесс.
        # На машине 3,5 ГБ это около 240 МБ на процесс. Результаты те же.
        vectors = np.load(VEC_FILE, mmap_mode="r")
        ids = np.load(IDS_FILE)
    except Exception as exc:  # noqa: BLE001 - любая проблема = работаем без индекса
        log.warning("индекс эмбеддингов не загрузился: %s", exc)
        return None
    if len(vectors) != len(ids):
        log.warning("индекс битый: векторов %d, id %d", len(vectors), len(ids))
        return None
    _index = (vectors, {int(item_id): row for row, item_id in enumerate(ids)})
    log.info("индекс эмбеддингов загружен: %d вещей", len(ids))
    return _index


def _get_encoder() -> Any:
    """Энкодер картинок. Тяжёлые веса грузятся один раз и только при первом вызове."""
    global _encoder, _encoder_tried
    if _encoder is not None or _encoder_tried:
        return _encoder
    _encoder_tried = True
    try:
        from sentence_transformers import SentenceTransformer

        _encoder = SentenceTransformer(MODEL_NAME)
        log.info("энкодер %s загружен", MODEL_NAME)
    except Exception as exc:  # noqa: BLE001 - на боте энкодера может не быть вовсе
        log.info("энкодер недоступен (%s) - визуальный сигнал выключен", exc)
        _encoder = None
    return _encoder


def available() -> bool:
    """Есть ли визуальный сигнал вообще: и индекс, и энкодер."""
    return _load_index() is not None and _get_encoder() is not None


def preload() -> None:
    """Прогреть индекс и энкодер заранее (фоновый поток на старте сервисов).

    Без прогрева первый разбор после рестарта ждёт ~20с загрузки весов CLIP и
    на экране выглядит зависшим. Запускать в отдельном потоке: загрузка блокирующая
    и тяжёлая, старт uvicorn/бота и /health она задерживать не должна. Ошибки глушим -
    без прогрева останется прежняя ленивая загрузка при первом скане.
    """
    try:
        _load_index()
        _get_encoder()
        log.info("эмбеддинги прогреты на старте")
    except Exception as exc:  # noqa: BLE001
        log.info("прогрев эмбеддингов не удался (%s) - будет ленивая загрузка", exc)


def encode_image(image: bytes) -> Any:
    """Вектор картинки (нормализованный). None, если энкодер недоступен."""
    encoder = _get_encoder()
    if encoder is None:
        return None
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(image)).convert("RGB")
        return encoder.encode([img], normalize_embeddings=True)[0]
    except Exception as exc:  # noqa: BLE001
        log.warning("не удалось посчитать вектор картинки: %s", exc)
        return None


def similarity(query_vector: Any, item_ids: list[int]) -> dict[int, float]:
    """Близость вектора запроса к каждой из вещей: id -> от 0 до 1.

    Вещи без вектора в индексе просто отсутствуют в ответе - вызывающий код
    трактует это как «визуального сигнала по ней нет», а не как ноль.
    """
    index = _load_index()
    if index is None or query_vector is None or not item_ids:
        return {}
    vectors, positions = index
    rows = [(item_id, positions[item_id]) for item_id in item_ids if item_id in positions]
    if not rows:
        return {}
    try:
        import numpy as np

        matrix = vectors[[row for _, row in rows]]
        scores = matrix @ np.asarray(query_vector, dtype=matrix.dtype)
        # косинус в [-1, 1] -> [0, 1]: отрицательные значения для нас всё равно «не похоже»
        return {item_id: float(max(0.0, min(1.0, (score + 1) / 2)))
                for (item_id, _), score in zip(rows, scores, strict=True)}
    except Exception as exc:  # noqa: BLE001
        log.warning("не удалось посчитать близость: %s", exc)
        return {}


def vector_of(item_id: int) -> Any:
    """Вектор вещи из индекса каталога. Энкодер не нужен - фото уже посчитано.

    Нужен для «Похожих на эту вещь»: ищем соседей по картинке карточки, а не
    по названию, которое в фидах бывает любым. None - вещи нет в индексе.
    """
    index = _load_index()
    if index is None:
        return None
    vectors, positions = index
    row = positions.get(int(item_id))
    return None if row is None else vectors[row]


def nearest(query_vector: Any, limit: int = 150) -> list[int]:
    """id ближайших вещей по всему индексу - для отбора кандидатов."""
    index = _load_index()
    if index is None or query_vector is None:
        return []
    vectors, positions = index
    try:
        import numpy as np

        scores = vectors @ np.asarray(query_vector, dtype=vectors.dtype)
        top = np.argsort(-scores)[:limit]
        by_row = {row: item_id for item_id, row in positions.items()}
        return [by_row[int(row)] for row in top if int(row) in by_row]
    except Exception as exc:  # noqa: BLE001
        log.warning("не удалось найти ближайших: %s", exc)
        return []


def reset_cache() -> None:
    """Для тестов и для перезагрузки индекса после ночного пересчёта."""
    global _index, _index_tried, _encoder, _encoder_tried
    _index = None
    _index_tried = False
    _encoder = None
    _encoder_tried = False
