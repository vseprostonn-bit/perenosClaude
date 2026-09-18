"""Лендинг и правовые страницы прямо из приложения.

Раньше их отдавал только nginx, и после выкатки нового лендинга это давало бы
разъезд: файл в репозитории обновился, а на сайте лежит то, что положили руками.
Теперь источник один - каталог `web/`, тот же, что возит deploy.sh.

Отдаём строго перечисленные файлы и картинки: никакого обхода каталога.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(tags=["site"])

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"
IMAGES_DIR = WEB_DIR / "images"

PAGES = {
    "index.html": "text/html; charset=utf-8",
    "oferta.html": "text/html; charset=utf-8",
    "privacy.html": "text/html; charset=utf-8",
}
IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
}

# Страницы меняются вместе с выкаткой, картинки живут долго
PAGE_CACHE = "public, max-age=300"
ASSET_CACHE = "public, max-age=604800"


def _page(name: str) -> FileResponse:
    path = WEB_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, media_type=PAGES[name],
                        headers={"Cache-Control": PAGE_CACHE})


@router.get("/", include_in_schema=False)
async def landing() -> FileResponse:
    return _page("index.html")


@router.get("/oferta.html", include_in_schema=False)
async def oferta() -> FileResponse:
    return _page("oferta.html")


@router.get("/privacy.html", include_in_schema=False)
async def privacy() -> FileResponse:
    return _page("privacy.html")


@router.get("/images/{filename}", include_in_schema=False)
async def image(filename: str) -> FileResponse:
    # Только имя файла: ни подкаталогов, ни выхода наверх
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=404, detail="not found")
    path = IMAGES_DIR / filename
    media = IMAGE_TYPES.get(path.suffix.lower())
    if media is None or not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, media_type=media,
                        headers={"Cache-Control": ASSET_CACHE})


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    path = IMAGES_DIR / "favicon-32.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": ASSET_CACHE})
