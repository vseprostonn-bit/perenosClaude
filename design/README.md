# Дизайн Образа — выдача 2026-08-25

> База: research-design-top-2026-08-25 + design-agent (§Образ) + references.md §7 + design-brief. Всё 0₽ (Магнифик у Саши, Figma/Spline free). Тёмная/светлая тема ТГ 4.5:1.

## Что внутри `obraz/design/`

| Файл | Что |
|---|---|
| `miniapp-01-onboarding.html` | Онбординг квиз 3 шага (размер S → стиль → бюджет), прогресс-бар, MainButton «Далее», пропуск — фаза 0 анкета |
| `miniapp-02-feed.html` | Лента образов masonry 2 колонки, карточка 4:5, слоты-чипы, 4 бейджа цены (WB/Lamoda/Ozon/ЯМ), липкий CTA «Открыть 3 бесплатно» |
| `miniapp-03-card.html` | Карточка образа: cover 4:5 + слоты с альтернативами + in_stock=false бейдж + sticky CTA |
| `miniapp-04-paywall.html` | Пейвол 3 тарифа 199/299/499 с якорем ~~990~~, средний «Популярный» подсвечен, доверие МИР/СБП/Робочеки, FAQ 4 |
| `landing.html` | Лендинг: Hero цифра (50·4·2мин) → Боль 3 → 3 шага → Демо ленты → Соцдок → Прайс якорь → FAQ → CTA каждые 1.5 экрана, липкий хедер |
| `creatives.html` | 3 концепции × 2 формата (1080×1080, 1080×1920): Боль/Выгода/Механика, текст ≤7 слов, промпты Магнифик |

## Палитра и типографика

- bg #FFF8F6, text #1A1A1E, accent CTA #FF4D6A, secondary #FF8FA3, border #F2E6E2. Тёмная ТГ #1A1212.
- Шрифты: Manrope 700 (заголовки) + Inter 400/500. Сетка 8px, радиус 16, 1 CTA-цвет.

## Промпты Магнифик (копипаст — собери у себя)

- Hero 3D: `isometric stack of fashion outfit cards, soft plastic, warm studio light, minimal pastel, coral #FF4D6A --ar 16:9 --style raw`
- Карточка: `flat lay outfit top/bottom/shoes/bag, light bg, soft shadow --ar 4:5`
- Иконки: `minimal line icons top bottom shoes bag accessory, coral #FF4D6A --ar 1:1`

## TG Mini App — чек-лист

- viewportStableHeight, safe area, без горизонтали 360px, thumb-zone
- themeParams светлая/тёмная проверены 4.5:1
- BackButton, MainButton, HapticFeedback, состояния empty/skeleton/ошибка/битый товар

## Чек-лист 12 дизайнера (selfcheck)

- [x] 8px, 4 цвета + #FF4D6A, 2 шрифта
- [x] 1 экран=1 действие, воздух 60%
- [x] F-паттерн
- [x] 1 CTA-цвет, липкий хедер, CTA/1.5 экрана
- [x] Соцдок цифрой (50 образов · 4 маркетплейса)
- [x] Прайс якорь ~~990~~→299, средний подсвечен
- [x] FAQ 3-4
- [x] Мобилка 360 без горизонтали
- [x] 3D 1 материал soft plastic
- [x] PAS/AIDA 1 месседж/блок
- [x] <2с, <150KB hero (скелетон, ленивая лента)
- [x] 4.5:1, фокус-стейты, обе темы ТГ

## Что дальше

- Ревью Саши → заменить плейсхолдеры на живые образы из матрицы (app/data) → Figma free → Spline 3D стопка образов
- Коммит в `Obraz-WB-OZON-AI` для Никитоса отдельным PR (скрины + html)

## Где агент

- Инструкции: `obraz/agents/design-agent.md` + `.claude/agents/designer.md` (§Образ) + `design-agent/references.md §7`
- Бриф/исследование: `obraz/docs/design-brief-2026-08-25.md` + `research/research-design-top-2026-08-25.md`
