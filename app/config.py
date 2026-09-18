from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""
    database_url: str = "sqlite+aiosqlite:///./obraz.db"
    free_limit: int = 5
    admin_tg_id: int = 0
    # Второй владелец: тоже без лимитов на разборы. Через запятую можно
    # добавить тестировщиков на время прогона.
    owner_tg_ids: str = ""
    # Ежедневный отчёт воронки шлётся admin_tg_id + всем этим id (через запятую).
    # Сюда добавляются партнёры, которым нужна та же сводка (например, Саша).
    report_tg_ids: str = ""

    # Фаза D: оплата
    public_base_url: str = "https://getobraz.ru"
    secret_key: str = "dev-secret-change-me"
    robokassa_merchant_login: str = ""
    robokassa_password1: str = ""
    robokassa_password2: str = ""
    robokassa_test_mode: bool = True
    referral_discount_percent: int = 15  # скидка приведённой блогеркой на первый месяц
    # Пользовательская рефералка «пригласи подругу». Цифры ставятся по расчёту
    # экономики: скидка это фактически стоимость привлечения, и она не должна
    # превышать предельный CAC.
    invite_discount_percent: int = 30      # скидка пригласившей на следующий платёж
    # Приглашённой даём не скидку, а разборы: три разбора стоят нам 1,5-3 руб,
    # а скидка на первый месяц - 88-222 руб. И бьёт это в её реальный страх
    # «заплачу, а вещи не найдутся», а не в цену.
    invite_friend_bonus_scans: int = 3
    invite_max_credits: int = 3            # потолок накопления, защита от накрутки
    bot_username: str = "obraz_style_bot"  # из него строится ссылка-приглашение
    blogger_share_percent: int = 15  # доля блогера с оплат приведённых

    # «Скрин в образ»: ИИ-разбор фото лука (GigaChat vision)
    gigachat_credentials: str = ""  # авторизационный ключ из ЛК developers.sber.ru
    lookscan_model: str = "GigaChat-2-Pro"  # vision умеют Pro и Max
    lookscan_free_scans: int = 1  # без подписки - разборов всего
    lookscan_daily_limit: int = 20  # с подпиской - разборов в день

    # Мини-приложение: раздаётся самим FastAPI по /app.
    # Telegram принимает только https, поэтому в дев-режиме кнопка не показывается.
    miniapp_url: str = ""  # пусто = public_base_url + /app

    # Обложки образов: генерация картинок (YandexART, ключ Саши)
    yandex_art_api_key: str = ""
    yandex_art_folder: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
