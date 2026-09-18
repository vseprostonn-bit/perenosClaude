"""Мини-приложение: раздача статики и API по контракту из брифа.

  GET  /app                     страница мини-аппа
  GET  /app/<файл>              её статика
  POST /api/scan                разбор фото -> вещи с карточками из каталога
  GET  /api/outfits             лента готовых образов
  GET  /api/outfits/{id}        состав образа
  GET  /api/scans                мои разборы, последние сверху
  GET  /api/scans/{id}           сохранённый разбор целиком
  GET  /api/similar/{item_id}   похожие на вещь
  POST /api/favorites/{item_id} лайк
  GET  /api/me, POST /api/me    профиль и настройки

Авторизация - заголовок X-Telegram-Init-Data, подпись проверяется на сервере
(app/services/telegram_auth.py). Без валидной подписи отдаём 401: мини-апп
открыт в интернете, и без проверки любой желающий читал бы чужие профили.

Контракт согласован с версткой в web/miniapp: если он меняется, меняется и
`api.js`. Модуль намеренно отдельный от pay.py, чтобы правки мини-аппа не
задевали оплату.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_scope
from app.models import Item, Outfit, User
from app.services import embeddings, garment_crop, scans
from app.services.catalog import WEAK_MIN, search_scored
from app.services.events import track
from app.services.lookscan import (
    SCAN_EVENT,
    analyze_look,
    can_scan,
    catalog_gender,
    item_visible,
)
from app.services.match_log import record_shown
from app.services.outfits import has_active_subscription
from app.services.telegram_auth import TelegramUser, verify_init_data
from app.services.users import get_or_create_user

router = APIRouter(tags=["miniapp"])

MINIAPP_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "miniapp"
IMAGES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "images"
ALLOWED_FILES = {"index.html", "styles.css", "app.js", "api.js"}
STYLES = {"casual", "office", "date", "sport", "basic", "smart"}


async def current_user(
    x_telegram_init_data: Annotated[str | None, Header()] = None,
) -> TelegramUser:
    """Пользовательница из подписанной initData. Иначе 401."""
    user = verify_init_data(x_telegram_init_data or "")
    if user is None:
        raise HTTPException(status_code=401, detail="Нет валидной подписи Telegram")
    return user


# ------------------------------------------------------------------ статика


@router.get("/app")
async def miniapp_index() -> FileResponse:
    index = MINIAPP_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Мини-апп не собран")
    # no-store: Telegram агрессивно кеширует мини-апп, из-за чего клиенты залипали
    # на старом HTML (относительные пути -> 404 -> пустой экран). Пусть тянет свежий.
    return FileResponse(
        index, media_type="text/html", headers={"Cache-Control": "no-store"}
    )


@router.get("/app/img/{filename}")
async def miniapp_image(filename: str) -> FileResponse:
    """Картинки мини-аппа отдаём под /app, а не /images.

    На проде статику по /images раздаёт nginx из своего каталога, и фотографии
    в приложении просто пропадали. Всё, что нужно мини-аппу, теперь живёт под
    тем же префиксом, что и он сам, - зависимость ровно одна.
    """
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=404, detail="Нет такого файла")
    media = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".svg": "image/svg+xml", ".webp": "image/webp",
    }.get(Path(filename).suffix.lower())
    path = IMAGES_DIR / filename
    if media is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Нет такого файла")
    # Картинки не меняются на месте: новая версия - новое имя файла
    return FileResponse(path, media_type=media,
                        headers={"Cache-Control": "public, max-age=604800"})


@router.get("/app/{filename}")
async def miniapp_asset(filename: str) -> FileResponse:
    # Отдаём только известные файлы: так каталог не превращается в файловый сервер.
    if filename not in ALLOWED_FILES:
        raise HTTPException(status_code=404, detail="Нет такого файла")
    path = MINIAPP_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Нет такого файла")
    media = {"css": "text/css", "js": "application/javascript"}.get(
        filename.rsplit(".", 1)[-1], "text/html"
    )
    return FileResponse(path, media_type=media, headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ общее


async def _user_row(session: AsyncSession, tg: TelegramUser) -> User:
    user, _ = await get_or_create_user(session, tg.id, tg.username, tg.first_name)
    return user


# ------------------------------------------------------------------ API


@router.post("/api/scan")
async def api_scan(
    tg: Annotated[TelegramUser, Depends(current_user)],
    photo: Annotated[UploadFile, File()],
) -> JSONResponse:
    """Разбор фото. Лимиты те же, что в боте: свои у подписки, свои у пробного."""
    async with session_scope() as session:
        user = await _user_row(session, tg)
        subscribed = await has_active_subscription(session, user.id)
        if not await can_scan(session, user.id, subscribed):
            return JSONResponse(
                {"error": "limit", "subscribed": subscribed}, status_code=402
            )

        photo_bytes = await photo.read()
        analysis = await analyze_look(photo_bytes)
        if analysis is None:
            return JSONResponse({"error": "scan_failed"}, status_code=502)
        # Невидимую/выдуманную вещь (низкая уверенность vision) не показываем.
        # Если видимых не осталось, разбор неудачный: пустой в «Мои разборы»
        # не пишем и лимит не тратим.
        visible = [look for look in analysis.items if item_visible(look)]
        if not analysis.is_outfit or not visible:
            return JSONResponse({"error": "not_outfit"}, status_code=422)

        # Событие = списание лимита. Неудачные попытки лимит не тратят.
        await track(
            session, user.id, SCAN_EVENT,
            {"items": str(len(visible)), "vibe": analysis.vibe, "src": "miniapp"},
        )

        # Визуальный сигнал - по вырезанной вещи, тот же путь, что в боте.
        visual_on = await asyncio.to_thread(embeddings.available)
        gender = catalog_gender(analysis.gender, user.style)
        entries: list[dict[str, Any]] = []
        for look in visible:
            item_vector: Any = None
            if visual_on:
                crop = garment_crop.crop_for(photo_bytes, look.category)
                if crop is not None:
                    item_vector = await asyncio.to_thread(embeddings.encode_image, crop)
            # Глубже трёх: первый кандидат - карточка, остальные уходят в
            # «Похожие». Скоринг и порядок те же, меняется только глубина.
            scored = await search_scored(
                session, look, gender=gender, limit=scans.MAX_PRODUCTS,
                photo_vector=item_vector,
            )
            confident = [m for m in scored if m.score >= WEAK_MIN]
            log_id = None
            if confident:
                log_id = await record_shown(session, user.id, look, confident[0], position=1)
            entries.append(scans.slot_entry(look, confident, log_id))

        # Разбор сохраняется целиком: к нему возвращаются из «Мои разборы» с
        # теми же вещами и ссылками, без нового запроса к vision и без лимита.
        scan = await scans.save_scan(
            session, user.id, "miniapp", analysis.vibe, gender, entries
        )
        return JSONResponse(scans.payload(scan))


@router.get("/api/scans")
async def api_scans(tg: Annotated[TelegramUser, Depends(current_user)]) -> list[dict[str, Any]]:
    """Мои разборы: и из бота, и из мини-аппа - разбор один, где бы ни делался."""
    async with session_scope() as session:
        rows = await scans.recent_scans(session, tg.id)
        return [scans.summary(row) for row in rows]


@router.get("/api/scans/{scan_id}")
async def api_scan_saved(
    scan_id: int, tg: Annotated[TelegramUser, Depends(current_user)]
) -> dict[str, Any]:
    """Сохранённый разбор. Лимит не тратит: всё уже найдено и оплачено."""
    async with session_scope() as session:
        scan = await scans.get_scan(session, tg.id, scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Разбор не найден")
        return scans.payload(scan)


@router.get("/api/outfits")
async def api_outfits(
    tg: Annotated[TelegramUser, Depends(current_user)],
    style: Annotated[str | None, Query()] = None,
    budget: Annotated[int | None, Query()] = None,
    gender: Annotated[str | None, Query()] = None,
) -> list[dict[str, Any]]:
    async with session_scope() as session:
        query = select(Outfit).where(Outfit.status == "published")
        if style in STYLES:
            query = query.where(Outfit.style == style)
        outfits = (await session.scalars(query.limit(60))).all()

        result = []
        for outfit in outfits:
            prices = [oi.item.price for oi in outfit.items if oi.item]
            price_from = min(prices) if prices else 0
            if budget and price_from > budget:
                continue
            if gender and any(oi.item and oi.item.gender not in (gender, "unisex")
                              for oi in outfit.items):
                continue
            result.append({
                "id": outfit.id,
                "title": outfit.title,
                "cover_url": outfit.cover_photo,
                "price_from": price_from,
                "style": outfit.style,
            })
        return result


@router.get("/api/outfits/{outfit_id}")
async def api_outfit(
    outfit_id: int, tg: Annotated[TelegramUser, Depends(current_user)]
) -> dict[str, Any]:
    async with session_scope() as session:
        outfit = await session.get(Outfit, outfit_id)
        if outfit is None or outfit.status != "published":
            raise HTTPException(status_code=404, detail="Образ не найден")
        return {
            "id": outfit.id,
            "title": outfit.title,
            "cover_url": outfit.cover_photo,
            "items": [
                {"slot": oi.slot, **scans.product_snapshot(oi.item)}
                for oi in outfit.items
                if oi.item
            ],
        }


@router.get("/api/similar/{item_id}")
async def api_similar(
    item_id: int, tg: Annotated[TelegramUser, Depends(current_user)]
) -> list[dict[str, Any]]:
    """Похожие на вещь из каталога - добор, когда вариантов из разбора мало.

    Кандидаты отбираются по картинке карточки из индекса, если она там есть:
    названия в фидах бывают любыми, а фото говорит о вещи честнее. Нет индекса -
    работает по тексту, как раньше.
    """
    from app.services.lookscan import LookItem

    async with session_scope() as session:
        item = await session.get(Item, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Вещь не найдена")
        look = LookItem(
            category=item.category, name=item.title,
            color=item.color or "", search_query=item.title,
        )
        vector = await asyncio.to_thread(embeddings.vector_of, item_id)
        scored = await search_scored(
            session, look, gender=item.gender, limit=scans.MAX_PRODUCTS + 1,
            photo_vector=vector,
        )
        return [
            scans.product_snapshot(m.item)
            for m in scored
            if m.item.id != item_id and m.score >= WEAK_MIN
        ][: scans.MAX_PRODUCTS]


@router.post("/api/favorites/{item_id}")
async def api_favorite(
    item_id: int, tg: Annotated[TelegramUser, Depends(current_user)]
) -> dict[str, Any]:
    async with session_scope() as session:
        user = await _user_row(session, tg)
        item = await session.get(Item, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Вещь не найдена")
        await track(session, user.id, "favorite", {"item_id": str(item_id), "src": "miniapp"})
        await session.commit()
        return {"ok": True, "id": item_id}


@router.get("/api/me")
async def api_me(tg: Annotated[TelegramUser, Depends(current_user)]) -> dict[str, Any]:
    async with session_scope() as session:
        user = await _user_row(session, tg)
        subscribed = await has_active_subscription(session, user.id)
        from app.services.lookscan import free_scans_for, scans_count

        used = await scans_count(session, user.id)
        free = await free_scans_for(session, user.id)
        await session.commit()
        return {
            "name": user.first_name or "красотка",
            "gender": "men" if (user.style or "") == "men" else "women",
            "size": user.size,
            "stores": (
                user.search_marketplaces.split(",") if user.search_marketplaces else []
            ),
            "subscription": {
                "active": subscribed,
                "plan": None,
                "scans_left": max(0, free - used) if not subscribed else None,
            },
        }


@router.post("/api/me")
async def api_save_me(
    tg: Annotated[TelegramUser, Depends(current_user)], patch: dict[str, Any]
) -> dict[str, Any]:
    """Сохраняем только то, что мини-апп вправе менять."""
    async with session_scope() as session:
        user = await _user_row(session, tg)
        if isinstance(patch.get("size"), str):
            user.size = patch["size"][:16]
        if isinstance(patch.get("stores"), list):
            codes = [str(s)[:16] for s in patch["stores"][:10]]
            user.search_marketplaces = ",".join(codes) if codes else None
        if patch.get("gender") in ("women", "men"):
            user.style = patch["gender"]
        await session.commit()
        return {"ok": True}
