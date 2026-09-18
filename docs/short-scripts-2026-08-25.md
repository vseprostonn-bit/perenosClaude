# Сценарии Shorts/Reels — 6 штук + промты Магнифик (видео + изображения)

Дата: 2026-08-25. База: content-matrix, research-creative-top, GROWTH-PLAYBOOK.
Цель: 4 клипа за 14 дней + 2 запасных, все через Магнифик (картинка Nano Banana → видео Kling 2.5 Pro), ≤2000 токенов/ген, 0-30₽.

## Правила (контент-фабрика short-form)
- 1 клип = 1 инсайт + 1 эмоция, 18-25с, вертикаль 9:16, хук 0-2с, CTA последние 2с.
- Текст на видео ≤7 слов, субтитры CapCut авто.
- Kling: duration 5с или 10с, cfg_scale 0.5, image ≥300×300, ≤10MB, aspect 1:2.5..2.5:1.

## Сценарии

### S1 — «За 30 сек готов» (учёба, low) — cover-01/02
**Хук (0-2с):** «3 часа на поиск образа? А так — 30 сек» (крупно, Manrope Bold)
**Сцены:** 0-5с флэтлей cover-01 → 5-10с свайп ленты бота (скрин) → 10-15с цены 4 площадок → 15-18с CTA
**Текст в видео:** «Образ за 30 сек → 4 площадки → где дешевле → бот в шапке»
**Kling промпт (image → video):**
```
prompt: "camera slowly zooms into fashion flat lay, gentle pan, soft warm lighting, minimal movement, editorial style"
negative_prompt: "text, watermark, fast motion, blur, distortion"
duration: "5"
cfg_scale: 0.5
image: "https://.../covers/cover-01-milk-total.png"  # заливаем на cdn или base64
```
**Звук:** тренд TikTok 2026 — спокойный lo-fi, 110 BPM.

### S2 — «1 юбка — 3 образа» (капсула) — cover-04
**Хук:** «1 юбка = 3 образа. Смотри»
**Сцены:** 0-6с юбка + таймер смены верха (3 клика) → 6-12с 3 лука рядом → 12-18с CTA
**Kling:**
```
prompt: "three outfits transform smoothly: same skirt with different tops, gentle transition, warm soft light, fashion editorial"
negative_prompt: "text, distortion, extra limbs"
duration: "5"
```

### S3 — «WB vs Lamoda где дешевле» (офис) — cover-05
**Хук:** «Та же юбка: WB 1200 vs Lamoda 2900»
**Сцены:** 0-5с сравнение цен → 5-12с образ целиком → 12-18с кнопка «где купить»
**Kling:**
```
prompt: "fashion outfit on cream background, subtle price tags floating, gentle camera orbit, warm light, minimal"
duration: "5"
```

### S4 — «Парень сказал вау» (свидание) — cover-03
**Хук:** «Сохрани на свидание — скажет вау»
**Сцены:** 0-5с платье+тренч флэтлей → 5-12с девушка в образе (Kling оживляет) → 12-18с CTA
**Kling:**
```
prompt: "model gently sways in burgundy dress and trench coat, soft romantic lighting, subtle wind in fabric, warm tones"
negative_prompt: "text, distorted face, extra fingers"
duration: "10"
cfg_scale: 0.5
```

### S5 — запасной «Офис без скуки 5/7» — cover-02
**Хук:** «Офис без скуки: 5 из 7»
**Kling:** как S3 но с пиджаком.

### S6 — запасной «Сохрани на свидание» — cover-09
**Хук:** «За 1200 выглядит на 12000»
**Kling:** как S1.

## Промты для изображений под шортсы (если нужен кадр которого нет в covers)
- Для S1 хук-кадра: `close-up of young woman holding phone showing fashion app, surprised happy expression, warm coral cream palette, vertical 9:16, clean --ar 9:16`
- Для цен: генерить в CapCut текстом, не в Магнифик.

## Сборка (CapCut free)
1. Импорт Kling-видео 5-10с + 2-3 фото covers
2. Хук 0-2с — крупный текст, scale 0.9→1.0, 200мс spring
3. Субтитры авто → стиль Bold, тень
4. Музыка тренд + звук «whoosh» на переходе
5. Экспорт 1080×1920, 30fps, ≤30MB

## Где лежат ассеты
- Исходные фото: assets/covers/
- Видео Kling: assets/videos/ (создастся после генерации)
- Готовые шортсы: assets/shorts/

## Генерация пачками (≤2000 токенов)
- Nano Banana 1K ~ ~800 токенов, 2K ~ ~1500 токенов — в лимите.
- Kling 5с ~ ~1200 токенов, 10с ~ ~1800 — тоже в лимите. Генерим 1 за раз, пауза 20с.
- После каждых 4 генераций — пауза 60с чтобы не словить 429 avg (10/сек на 2 мин).

## Чек-лист
- [ ] 4 клипа готовы (S1-S4) в assets/shorts/
- [ ] Каждый ≤25с, хук 0-2с, CTA, без водяных
- [ ] Залиты в ВК Клипы + ТГ + Shorts (расписание в content-plan-14d)
