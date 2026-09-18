"""FastAPI-приложение: health, страницы оплаты и мини-приложение.

TG-webhook для прода добавится в фазе F.
"""

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import ensure_schema
from app.routes.miniapp import router as miniapp_router
from app.routes.pay import router as pay_router
from app.routes.site import router as site_router
from app.services import embeddings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Догоняем схему на старте: mini app пишет в match_log, которого на проде
    # ещё нет. Alembic на проде не гоняем, поэтому ensure_schema.
    await ensure_schema()
    # Прогрев CLIP в фоне: без него первый разбор ждёт ~20с загрузки весов и
    # выглядит зависшим. Поток демонский, старт и /health не блокирует.
    threading.Thread(target=embeddings.preload, daemon=True).start()
    yield


app = FastAPI(title="Obraz", docs_url=None, redoc_url=None, lifespan=lifespan)
app.include_router(pay_router)
app.include_router(miniapp_router)
app.include_router(site_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
