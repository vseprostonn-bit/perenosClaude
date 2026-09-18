# Доступы Образа — шаблон (локально, НЕ пушить в git!)

> Заполни руками по чек-листу `docs/accounts-checklist-2026-08-25.md`. Логины — единый стиль `obraz.*`. Пароли сгенерированы стойкие — смени при реги если сервис не принимает символы. Храни в менеджере паролей (Bitwarden free), этот файл — только временно у тебя на диске.

**ВАЖНО:** файл в `.gitignore` — не коммить. Инфра (домен/почта info@*/VPS/BotFather) — делает Yorren, здесь не заводим.

| # | Сервис | Логин (используй) | Пароль (измени при нужде) | Почта для реги | 2FA | Ссылка | Статус |
|---|---|---|---|---|---|---|---|
| 1 | TG-канал Образа | @obraz_style | — (привязка к TG-аккаунту) | — | TG | t.me | [ ] |
| 2 | ControllerBot | @obraz_style | — | — | TG | t.me/ControllerBot | [ ] |
| 3 | Telegraph | obraz_style | — | — | TG | telegra.ph | [ ] |
| 4 | TGScan-боты | obraz_style | — | — | TG | @TGStat_Bot | [ ] |
| 5 | TGStat free | obraz.style | `Obraz!Tg5t_9kL2vQ8x` | yandex-почта* | — | tgstat.ru | [ ] |
| 6 | Telemetr free | obraz.style | `Obraz!Tlm_4pW7nR1y` | yandex-почта | — | telemetr.me | [ ] |
| 7 | Telega.in free-поиск | obraz.style | `Obraz!Tlg_6jK3mZ5a` | yandex-почта | — | telega.in | [ ] |
| 8 | Epicstars free-поиск | obraz.style | `Obraz!Epc_8hV2qL9w` | yandex-почта | — | epicstars.com | [ ] |
| 9 | Яндекс Wordstat | obraz.style@yandex.ru | `Obraz!Wrd_3bN8cF2k` | yandex | — | wordstat.yandex.ru | [ ] |
| 10 | Google Trends / Google | obraz.style.2026@gmail.com | `Obraz!Ggl_5tY9uI1o` | gmail | вкл | trends.google.ru | [ ] |
| 11 | Pinterest Trends | obraz.style | `Obraz!Pin_7eR4tJ6h` | yandex/gmail | — | trends.pinterest.com | [ ] |
| 12 | SimilarWeb free | obraz.style | `Obraz!Smw_2qA8zX4c` | yandex/gmail | — | similarweb.com | [ ] |
| 13 | VK группа + Клипы | obraz.style | `Obraz!Vkk_9fD3gH7j` | VK ID (телефон) | вкл | vk.com | [ ] |
| 14 | YouTube / Shorts | obraz.style.2026@gmail.com | `Obraz!Ytb_1kL5pQ8v` | gmail | вкл | youtube.com | [ ] |
| 15 | Rutube | obraz.style | `Obraz!Rtb_6nM2bV9x` | VK ID/почта | — | rutube.ru | [ ] |
| 16 | Дзен | obraz.style@yandex.ru | `Obraz!Dzn_4cF7hK2m` | yandex | — | dzen.ru | [ ] |
| 17 | Pikabu | obraz_style | `Obraz!Pkb_8vN3jL5q` | yandex-почта | — | pikabu.ru | [ ] |
| 18 | TG-каталоги (tlgrm) | obraz.style | `Obraz!Tlg_3wQ6eR9t` | — | — | tlgrm.ru | [ ] |
| 19 | Магнифик (у Саши) | obraz_style | — (локальный софт) | — | — | — | [x] |
| 20 | CapCut desktop | obraz.style | `Obraz!Ccp_5aS8dF1g` | gmail/yandex | — | capcut.com | [ ] |
| 21 | Kandinsky 3.1 | obraz.style@yandex.ru | `Obraz!Knd_9zX2cV6b` | yandex | — | fusionbrain.ai | [ ] |
| 22 | GigaChat Vision | obraz.style@yandex.ru | `Obraz!Ggc_4hJ7kL2n` | yandex | — | gigachat.sber.ru | [ ] |
| 23 | Leonardo.ai | obraz.style.2026@gmail.com | `Obraz!Leo_6mK9pQ2w` | gmail | — | leonardo.ai | [ ] |
| 24 | Remove.bg | obraz.style.2026@gmail.com | `Obraz!Rmb_3eR7tY2u` | gmail | — | remove.bg | [ ] |
| 25 | Photoroom free | obraz.style.2026@gmail.com | `Obraz!Phr_8iO4pL6k` | gmail | — | photoroom.com | [ ] |
| 26 | ClipDrop / Yandex ART | obraz.style | `Obraz!Clp_1qW4eR7t` | yandex/gmail | — | clipdrop.co | [ ] |
| 27 | Google Sheets / Drive | obraz.style.2026@gmail.com | `Obraz!Gsh_9oI2uY5t` | gmail | вкл | drive.google.com | [ ] |
| 28 | Notion free | obraz.style.2026@gmail.com | `Obraz!Ntn_4aS7dF2h` | gmail | — | notion.so | [ ] |
| 29 | Airtable free (альт Notion) | obraz.style.2026@gmail.com | `Obraz!Atb_6jK8l2zX` | gmail | — | airtable.com | [ ] |

\* Яндекс-почту заводит Yorren как `info@obraz.*` на домене — для этих сервисов используй её как только появится; до этого — временная yandex/gmail и потом сменить.

**Инфра (не заводим, Yorren):** домен, почта info@*, VPS/Coolify, @obraz_bot (BotFather) — токен в .env.

**После реги:** проставь [x] в Статус, включи 2FA где есть, сохрани recovery-коды в Bitwarden. Этот файл удали или перенеси в сейф после переноса в менеджер.

**Где лежит:** `02_growth-factory/obraz/docs/credentials-OBRAZ.template.md` (локально, в .gitignore)
