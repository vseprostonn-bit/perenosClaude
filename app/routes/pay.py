"""Страница пейвола и вебхук Robokassa.

GET /pay?t=<токен>  - тариф и кнопка оплаты (токен подписан, из бота)
POST /pay/go        - создать платёж и уйти на Robokassa
POST /pay/result    - ResultURL Robokassa: подпись + идемпотентность
GET /pay/success|fail - страницы результата
"""

from contextlib import suppress
from pathlib import Path
from typing import Annotated

from aiogram import Bot
from fastapi import APIRouter, Form, Query
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import texts
from app.config import get_settings
from app.db import session_scope
from app.models import User
from app.services.events import track
from app.services.payments import (
    create_payment,
    make_pay_token,
    offer_for,
    parse_pay_token,
    process_successful_payment,
    robokassa_payment_url,
    verify_result_signature,
)

router = APIRouter(prefix="/pay", tags=["pay"])
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

BOT_LINK = "https://t.me/obraz_style_bot"


@router.get("", response_class=HTMLResponse)
async def pay_page(request: Request, t: Annotated[str, Query()] = "") -> HTMLResponse:
    user_id = parse_pay_token(t)
    if user_id is None:
        return templates.TemplateResponse(
            request, "pay_expired.html", {"bot_link": BOT_LINK}, status_code=400
        )
    async with session_scope() as session:
        user = await session.get(User, user_id)
        if user is None:
            return templates.TemplateResponse(
                request, "pay_expired.html", {"bot_link": BOT_LINK}, status_code=400
            )
        offer = await offer_for(session, user)
    payments_ready = bool(get_settings().robokassa_merchant_login)
    return templates.TemplateResponse(
        request,
        "pay.html",
        {
            "offer": offer,
            "token": t,
            "payments_ready": payments_ready,
            "bot_link": BOT_LINK,
        },
    )


@router.post("/go")
async def pay_go(t: Annotated[str, Form()]) -> RedirectResponse:
    user_id = parse_pay_token(t)
    if user_id is None:
        return RedirectResponse(url="/pay?t=", status_code=303)
    async with session_scope() as session:
        user = await session.get(User, user_id)
        if user is None:
            return RedirectResponse(url="/pay?t=", status_code=303)
        payment, offer = await create_payment(session, user)
        await track(session, user.id, "paywall_click", {"price": str(offer.price)})
    url = robokassa_payment_url(
        payment.inv_id, payment.amount, "Подписка «Образ», 30 дней"
    )
    return RedirectResponse(url=url, status_code=303)


@router.post("/result", response_class=PlainTextResponse)
async def pay_result(
    OutSum: Annotated[str, Form()],
    InvId: Annotated[str, Form()],
    SignatureValue: Annotated[str, Form()],
) -> PlainTextResponse:
    if not verify_result_signature(OutSum, InvId, SignatureValue):
        return PlainTextResponse("bad sign", status_code=400)
    async with session_scope() as session:
        user_id = await process_successful_payment(session, int(InvId), OutSum)
    if user_id is not None:
        await _notify_user(user_id)
    return PlainTextResponse(f"OK{InvId}")


@router.get("/success", response_class=HTMLResponse)
async def pay_success(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "pay_success.html", {"bot_link": BOT_LINK})


@router.get("/fail", response_class=HTMLResponse)
async def pay_fail(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "pay_fail.html", {"bot_link": BOT_LINK})


async def _notify_user(user_id: int) -> None:
    token = get_settings().bot_token
    if not token:
        return
    with suppress(Exception):
        bot = Bot(token=token)
        try:
            await bot.send_message(user_id, texts.SUBSCRIPTION_ACTIVATED)
        finally:
            await bot.session.close()


def pay_url_for(user_id: int) -> str:
    return f"{get_settings().public_base_url}/pay?t={make_pay_token(user_id)}"
