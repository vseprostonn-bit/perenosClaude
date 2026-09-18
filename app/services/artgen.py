"""Генерация обложек образов через YandexART (async imageGeneration).

Ключ - от Яндекс Облака (Саша). GigaChat vision картинки не отдаёт,
поэтому визуал образов рисует YandexART: см. plans/2026-08-27-skrin-v-obraz.md.
"""

import asyncio
import base64
import json
import urllib.error
import urllib.request
from collections.abc import Mapping

from app.config import get_settings

_START_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/imageGenerationAsync"
_OP_URL = "https://operation.api.cloud.yandex.net/operations/"

STYLE_HINT = (
    "фотореалистичное модное фото, девушка в полный рост, естественная поза, "
    "городская улица, мягкий дневной свет, эстетика Pinterest, без текста и логотипов"
)


def _post(url: str, key: str, body: Mapping[str, object]) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Api-Key {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data: dict = json.loads(resp.read())
    return data


def _get(url: str, key: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Api-Key {key}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data: dict = json.loads(resp.read())
    return data


async def generate_cover(prompt: str) -> bytes | None:
    """Рисует обложку по описанию образа. None - ключ не задан или ошибка."""
    settings = get_settings()
    key, folder = settings.yandex_art_api_key, settings.yandex_art_folder
    if not (key and folder):
        return None

    body = {
        "modelUri": f"art://{folder}/yandex-art/latest",
        "generationOptions": {"aspectRatio": {"widthRatio": "3", "heightRatio": "4"}},
        "messages": [{"weight": "1", "text": f"{prompt}. {STYLE_HINT}"}],
    }
    try:
        op = await asyncio.to_thread(_post, _START_URL, key, body)
        op_id = op["id"]
        for _ in range(40):  # до ~2 минут
            await asyncio.sleep(3)
            status = await asyncio.to_thread(_get, _OP_URL + op_id, key)
            if status.get("done"):
                if "response" in status:
                    return base64.b64decode(status["response"]["image"])
                return None
    except (urllib.error.URLError, KeyError, ValueError):
        return None
    return None
