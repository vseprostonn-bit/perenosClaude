# Бриф: генерация визуального контента Образ — Магнифик + Kandinsky (0₽)

Дата: 2026-08-25. Автор: фабрика + дизайн-агент. Связь: content-generation-brief, research-creative-top, content-matrix.

## Цель
Сгенерировать ВЕСЬ визуальный контент фазы 0 бесплатно: обложки образов (50-100), креативы для посевов (6), 3D hero, аватар. Сохранить локально в `obraz/assets/`, НЕ пушить до команды Саши.

## Критерии готовности
- [ ] 10 обложек в `assets/covers/` (5 из матрицы + 5 шаблонов)
- [ ] 6 креативов в `assets/creatives/` (3 концепции × 1:1 + 9:16)
- [ ] 1 3D-стопка в `assets/hero/`
- [ ] 1 аватар + 1 обложка канала в `assets/brand/`
- [ ] `assets/prompt-log.md` — все промпты с параметрами

## Инструменты (0₽)
- **Магнифик** (локальный у Саши) — основной, безлимит
- **Kandinsky 3.1** — fusionbrain.ai, Яндекс-аккаунт, бесплатно
- **CapCut** — сборка видео из кадров

---

## П1. ОБЛОЖКИ ОБРАЗОВ (50-100 шт)

### Стиль (единый для всех)
Фотореалистичный флэтлей одежды на модели или без, тёплый свет, кремовый/персиковый фон, мягкие тени. Бренд-цвета: крем #FFF8F6, коралл #FF4D6A, персик #FFD5C2. Формат 4:5 (1080×1350) — как в ленте мини-аппа.

### Промпты (копипаст в Магнифик/Kandinsky)

**О1. Молочный тотал (учёба, low):**
```
flat lay fashion outfit on cream background: beige oversized top, black midi skirt, white loafers, crossbody bag, warm soft lighting, minimal pastel tones, coral accent, photorealistic, editorial style --ar 4:5 --style raw
```

**О2. Смарт-кэжуал (офис, mid):**
```
smart casual outfit flat lay: grey blazer, white t-shirt, blue jeans, nude heels, structured tote bag, warm studio light, cream background, soft shadows, fashion editorial --ar 4:5 --style raw
```

**О3. Свидание (вечер, mid):**
```
date night outfit flat lay: burgundy slip dress, camel trench coat, black ankle boots, small gold jewelry, warm romantic lighting, cream and peach tones, editorial fashion photo --ar 4:5 --style raw
```

**О4. Капсула 1 юбка 3 образа (база, low):**
```
capsule wardrobe flat lay: one beige midi skirt paired with three different tops (white tee, black turtleneck, striped blouse), minimal layout, warm light, cream background, fashion styling grid --ar 4:5 --style raw
```

**О5. Премиум офис (делов, high):**
```
premium office outfit flat lay: tailored beige suit, silk blouse, leather tote, pointed heels, luxury minimal, warm studio lighting, cream background, editorial --ar 4:5 --style raw
```

**О6-О10. Шаблоны (генерить по аналогии, менять вещи):**
```
О6: autumn cozy outfit flat lay: oversized knit sweater, wide-leg pants, white sneakers, tote bag, warm light --ar 4:5 --style raw
О7: student budget outfit: simple hoodie, pleated skirt, canvas shoes, backpack, warm cream tones --ar 4:5 --style raw
О8: office to evening transition outfit: blazer over dress, switch heels to flats, warm lighting --ar 4:5 --style raw
О9: weekend casual: denim jacket, white dress, sandals, straw bag, soft natural light --ar 4:5 --style raw
О10: autumn capsule 10 items grid layout: tops bottoms shoes accessories, warm tones, organized flat lay --ar 4:5 --style raw
```

### Параметры генерации
- Магнифик: разрешение 1080×1350, стиль «фотореализм» или «редакционный», без текста
- Kandinsky: модель 3.1, размер 1024×1280 (ближайший к 4:5), guidance 7-8, steps 30-40
- Если фон холодный — добавить `warm tones, cream background` в промпт

---

## П2. КРЕАТИВЫ ДЛЯ ПОСЕВОВ (3 концепции × 2 формата)

### К1 «Боль» — 1080×1080 и 1080×1920
**Инсайт:** девушка 3 часа листает поиск, не находит
**Хук:** «3 часа на поиск образа?»
**Визуал:** девушка с телефоном, усталая, вокруг хаос скриншотов
```
К1-1:1: young woman scrolling phone tired, surrounded by floating fashion screenshots and search results, frustrated expression, warm coral and cream color palette, social media ad style, bold text space at top, clean composition --ar 1:1 --style raw
К1-9:16: young woman scrolling phone tired, surrounded by floating fashion screenshots, frustrated, warm coral cream palette, vertical social media ad, text space top, clean --ar 9:16 --style raw
```
**Текст на крео (добавить в CapCut):** «3 часа на поиск образа? → Образ за 30 сек → ссылка в шапке»

### К2 «Выгода» — 1080×1080 и 1080×1920
**Инсайт:** готовый образ дешевле ТЦ
**Хук:** «Собрала 3 образа дешевле чем 1 в ТЦ»
**Визуал:** довольная девушка в образе, рядом цены «ТЦ 12 000 ₽ → Образ 2 400 ₽»
```
К2-1:1: happy young woman in stylish outfit holding phone showing shopping app, price comparison floating (12000 vs 2400), warm coral cream palette, social media ad, bold text space, clean composition --ar 1:1 --style raw
К2-9:16: happy young woman in stylish outfit holding phone, price comparison floating, warm coral cream palette, vertical ad, text space top, clean --ar 9:16 --style raw
```
**Текст:** «Собрала 3 образа дешевле чем 1 в ТЦ → 199₽/мес → промокод -15%»

### К3 «Механика» — 1080×1080 и 1080×1920
**Инсайт:** 4 площадки в 1 кнопке
**Хук:** «4 маркетплейса — 1 кнопка»
**Визуал:** экран телефона с лентой образов, кнопки «где купить» светятся
```
К3-1:1: smartphone screen showing fashion outfit feed with buy buttons, 4 marketplace logos floating around, warm coral cream palette, social media ad, clean minimal, text space --ar 1:1 --style raw
К3-9:16: smartphone screen fashion outfit feed with glowing buy buttons, 4 marketplace icons, warm coral cream palette, vertical ad, clean minimal --ar 9:16 --style raw
```
**Текст:** «4 площадки — 1 кнопка → где купить дешевле → бот в шапке»

### Сборка в CapCut
1. Импорт картинки из Магнифик/Кандинский
2. Добавить текст (шрифт Manrope Bold, белый, тень чёрная)
3. Добавить логотип «Образ» в угол (из `design/landing.html` можно скринить)
4. Экспорт 1080×1080 или 1080×1920, без водяных

---

## П3. 3D-СТОПКА ДЛЯ ЛЕНДИНГА

Заменяет CSS-заглушку в `web/index.html` (hero-visual). Формат 16:9, изометрия.
```
3D hero: isometric stack of 5 fashion outfit cards, soft plastic material, warm studio light, coral #FF4D6A and peach gradients, minimal pastel background, soft shadows, 8k render --ar 16:9 --style raw
```
**Альтернатива (если Магнифик не даёт изометрию):**
```
3D isometric stack of fashion cards, clay render, warm lighting, coral and cream, minimal --ar 16:9
```
**Вставка в лендинг:** заменить `<div class="card-stack">...</div>` на `<img src="assets/hero/3d-stack.png">` с теми же классами.

---

## П4. АВАТАР + ОБЛОЖКА КАНАЛА

**Аватар 512×512:**
```
minimal logo icon for fashion app: letter O with outfit hanger, coral #FF4D6A on cream background, rounded, modern, clean --ar 1:1 --style raw
```
**Обложка канала 1280×720:**
```
fashion app banner: warm gradient cream to peach, minimal outfit icons, text space center, coral accents, modern minimal --ar 16:9 --style raw
```
(Текст «Образ — готовые луки» добавить в CapCut)

---

## Ограничения и риски
- Только бесплатные генерации. Кандинский лимит ~50/день на фри — хватит на 10 обложек + 6 креативов.
- Фотореализм одежды у Кандинского средний → фолбэк: стилизованные флэтлеи (без лиц, только одежда).
- Магнифик — руками Саши, я готовлю промпты и параметры.
- Все файлы в `obraz/assets/`, НЕ пушить до команды.
- Если Кандинский просит верификацию → использовать только Магнифик.

## Порядок действий
1. Саша открывает Магнифик → генерит по промптам П1 (10 обложек)
2. Саша открывает Кандинский → генерит П2 (6 креативов) если Магнифик не даёт текст
3. Саша собирает текст в CapCut → экспорт
4. П3 и П4 — по остаточному принципу
5. Всё складываем в `obraz/assets/` по папкам
