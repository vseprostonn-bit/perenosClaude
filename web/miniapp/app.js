/* Мини-апп «Образ»: роутинг, отрисовка, интеграция с Telegram.
 * Данные берутся только через API из api.js - вёрстка не знает, заглушка это или прод.
 */

const tg = window.Telegram && window.Telegram.WebApp;

const state = {
  screen: "home",
  gender: "women",      // главный сегмент - женский, мужской включается тумблером
  me: null,
  scan: null,            // открытый разбор: свежий или из «Мои разборы»
  scanSaved: false,      // открыт из истории - фото пользовательницы нет, цены на момент разбора
  similar: null,         // экран «Похожие»: вещь из разбора и её варианты
  outfit: null,          // открытая карточка образа
  favorites: [],
  filters: { style: null, budget: null },
  photoUrl: null,        // превью загруженного фото
};

const SLOT_NAMES = {
  top: "Верх", bottom: "Низ", dress: "Платье", outerwear: "Верхняя одежда",
  shoes: "Обувь", bag: "Сумка", accessory: "Аксессуар",
};
const slotName = (slot) => SLOT_NAMES[slot] || slot;

// Знак бренда, см. brand/logo/README.md в маркетинговом репозитории.
function markSvg(size) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 52 52" fill="none" aria-hidden="true">
    <rect x="6" y="13" width="26" height="26" rx="8" stroke="currentColor" stroke-opacity=".38" stroke-width="2.6"/>
    <rect x="20" y="13" width="26" height="26" rx="8" stroke="currentColor" stroke-width="2.6"/>
    <path d="M26 19.6c.55 4.1 2.7 6.25 6.8 6.8-4.1.55-6.25 2.7-6.8 6.8-.55-4.1-2.7-6.25-6.8-6.8 4.1-.55 6.25-2.7 6.8-6.8z" fill="var(--accent)"/>
  </svg>`;
}


// Картинка может не дойти: пропал интернет, магазин отдал битую ссылку,
// фид сменил адрес. Вместо сломанной иконки показываем спокойную заглушку -
// в приложении про одежду сломанное фото выглядит как сломанный продукт.
const PLACEHOLDER =
  "data:image/svg+xml;charset=utf-8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
       <rect width="100" height="100" fill="#FBEDE8"/>
       <g fill="none" stroke="#C9B4AE" stroke-width="3" stroke-linecap="round">
         <rect x="26" y="32" width="48" height="40" rx="8"/>
         <path d="M38 32l4-6h16l4 6"/><circle cx="50" cy="52" r="10"/>
       </g>
     </svg>`
  );

document.addEventListener(
  "error",
  (e) => {
    const el = e.target;
    if (el && el.tagName === "IMG" && el.src !== PLACEHOLDER) {
      el.src = PLACEHOLDER;
      el.classList.add("img-fallback");
    }
  },
  true
);

const $ = (sel) => document.querySelector(sel);
const view = () => $("#view");

function plural(n, one, few, many) {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b > 1 && b < 5) return few;
  if (b === 1) return one;
  return many;
}
const things = (n) => `${n} ${plural(n, "вещь", "вещи", "вещей")}`;

const rub = (n) => new Intl.NumberFormat("ru-RU").format(n) + " ₽";
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

function haptic(kind = "impact") {
  if (!tg || !tg.HapticFeedback) return;
  if (kind === "impact") tg.HapticFeedback.impactOccurred("light");
  else tg.HapticFeedback.notificationOccurred(kind);
}

function toast(text) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.add("on");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("on"), 2000);
}

/* ---------- роутер ---------- */

const screens = {};

function go(name, opts = {}) {
  state.screen = name;
  window.scrollTo({ top: 0 });
  render();
  if (!opts.silent) haptic();
}

function render() {
  const fn = screens[state.screen] || screens.home;
  view().innerHTML = `<div class="screen">${fn()}</div>`;
  syncNav();
  bindBackButton();
}

function syncNav() {
  const map = { home: "home", scan: "scan", result: "scan", similar: "scan", feed: "feed", card: "feed", favorites: "favorites", profile: "profile", paywall: "profile" };
  const active = map[state.screen] || "home";
  document.querySelectorAll(".nav button").forEach((b) => {
    b.classList.toggle("on", b.dataset.tab === active);
  });
}

// Куда ведёт «назад» с вложенного экрана. Одна таблица и для кнопки в шапке
// Telegram, и для решения, показывать ли её вообще.
const BACK = { result: "scan", similar: "result", card: "feed", paywall: "profile" };

// Родные кнопки Telegram: «назад» на вложенных экранах, скрыта на корневых.
function bindBackButton() {
  if (!tg || !tg.BackButton) return;
  if (BACK[state.screen]) tg.BackButton.show(); else tg.BackButton.hide();
}

/* ---------- экраны ---------- */

screens.home = () => {
  const name = state.me && state.me.name ? state.me.name : "красотка";
  const left = state.me && state.me.subscription ? state.me.subscription.scans_left : 3;
  return `
  <div class="top">
    <div class="logo">${markSvg(26)}<span>ОБРАЗ</span></div>
    <div class="avatar" data-go="profile">${esc(name[0] || "О")}</div>
  </div>

  <div class="hero">
    <h1>Привет, ${esc(name)}</h1>
    <p class="muted">Кинь фото лука - соберу его из реальных вещей с ценами. Или листай готовые образы.</p>
  </div>

  <div style="padding:0 20px 14px">
    ${genderSwitch()}
  </div>

  ${shopsRow()}

  <div class="actions">
    <button class="act scan" data-go="scan">
      
      <span class="badge">${left > 0 ? `${left} разбора бесплатно` : "наша фишка"}</span>
      <h3>Разобрать лук по фото</h3>
      <p>Скрин из соцсети или фото с улицы - вещи с ценами и кнопкой купить</p>
    </button>
    <button class="act feed" data-go="feed">
      <span class="glyph"><svg class="ic-lg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4l1.9 4.6 4.9.4-3.7 3.2 1.1 4.8L12 14.6 7.8 17l1.1-4.8L5.2 9l4.9-.4z"/></svg></span>
      <h3>Готовые образы</h3>
      <p>Подборки под твой стиль, размер и бюджет</p>
    </button>
  </div>

  <div class="section-h"><h2>Образ дня</h2><button data-go="feed">все →</button></div>
  <div class="rail" id="rail"><div class="muted" style="padding:0 0 10px">Загружаю...</div></div>`;
};

screens.onboarding = () => `
  <div class="top"><div class="title">Пара вопросов<small>Чтобы подбирать твой размер</small></div></div>
  <div class="hero">
    <h1>Кому подбираем?</h1>
    <p class="muted">Можно поменять в любой момент в профиле.</p>
  </div>
  <div style="padding:0 20px 16px">${genderSwitch()}</div>

  <div class="section-h"><h2>Размер</h2></div>
  <div class="filters">
    ${["XS", "S", "M", "L", "XL"].map((s) => `
      <button class="chip ${state.me && state.me.size === s ? "on" : ""}" data-size="${s}">${s}</button>
    `).join("")}
  </div>

  <div style="padding:14px 20px 8px">
    <button class="btn-primary" data-onboard-done="1">Готово</button>
  </div>
  <p class="muted" style="padding:4px 20px 20px">Займёт секунду, зато не покажу вещь, которой нет в твоём размере.</p>`;

screens.scan = () => `
  <div class="top">
    <div class="title">Разбор лука<small>Фото - вещи - цены за 30 секунд</small></div>
  </div>

  <div style="padding:0 20px 12px">${genderSwitch()}</div>

  <div class="upload">
    <div class="glyph"><svg class="ic-lg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="6" width="18" height="14" rx="3"/><circle cx="12" cy="13" r="3.4"/><path d="M8 6l1.4-2h5.2L16 6"/></svg></div>
    <h3>Загрузи фото образа</h3>
    <p class="muted">Скрин из соцсети, фото с улицы или витрины. Главное - чтобы вещи было видно целиком.</p>
    <div class="row">
      <button class="btn-primary" id="pick">Выбрать фото</button>
    </div>
    <input type="file" id="file" accept="image/*" class="hidden">
  </div>

  <div id="history"></div>

  <div class="section-h"><h2>Что получится</h2></div>
  <div class="items">
    <div class="item">
      <img src="/app/img/item-shirt.jpg" alt="">
      <div class="info">
        <span class="slot">Пример</span>
        <span class="match high">она самая</span>
        <div class="name">Каждая вещь с фото, ценой и магазином</div>
        <div class="store">${SHOPS.join(", ")}</div>
      </div>
    </div>
  </div>`;

screens.loading = () => `
  <div class="loader">
    <div class="ring"></div>
    <h3>Разбираю образ</h3>
    <p class="muted">Обычно занимает 20-30 секунд</p>
    <div class="steps" id="steps">
      <div data-step="0">Смотрю, что на фото</div>
      <div data-step="1">Раскладываю на вещи</div>
      <div data-step="2">Ищу похожие в каталоге</div>
    </div>
  </div>`;

screens.result = () => {
  const s = state.scan;
  if (!s) return screens.scan();
  const total = s.items.reduce((sum, i) => sum + (i.products[0] ? i.products[0].price : 0), 0);
  const [vibeHead, vibeTail] = (s.vibe || "").split(" - ");
  // Фото пользовательницы на сервере не храним, поэтому у разбора из истории
  // шапка без кадра. Подставлять чужое фото с подписью «твоё фото» - обман.
  const hero = state.photoUrl
    ? `<div class="look-hero">
         <span class="tag">твоё фото</span>
         <img src="${esc(state.photoUrl)}" alt="">
         <div class="vibe"><b>${esc(vibeHead)}</b><span>${esc(vibeTail || "")}</span></div>
       </div>`
    : `<div class="look-head">
         <span class="tag">разбор от ${esc(s.date_label || "")}</span>
         <b>${esc(vibeHead || "Разбор образа")}</b>
         ${vibeTail ? `<span>${esc(vibeTail)}</span>` : ""}
       </div>`;
  return `
  <div class="top">
    <button class="back" data-go="scan">‹</button>
    <div class="title">${state.scanSaved ? "Сохранённый разбор" : "Разобрала твой лук"}<small>${things(s.items.length)} · нашла в наличии</small></div>
  </div>

  ${hero}

  <p class="muted" style="padding:12px 20px 4px">Собрала из реальных вещей - жми «Купить». Не то? Жми «Похожие» - покажу другие варианты этой вещи.</p>

  <div class="items">
    ${s.items.map((item, idx) => itemCard(item, idx)).join("")}
  </div>

  <div class="total">
    <div><div class="s">Весь образ</div></div>
    <div class="p">${rub(total)}</div>
  </div>
  ${state.scanSaved ? `<p class="muted note">Цены - на момент разбора, в магазине могут отличаться.</p>` : ""}

  <div style="padding:6px 20px 10px"><button class="btn-ghost" data-go="scan">Разобрать ещё лук</button></div>`;
};

// «Похожие» - это остальные кандидаты той же вещи с фото, от самого похожего.
// Если их мало, добираем из каталога по картинке первой карточки.
screens.similar = () => {
  const sim = state.similar;
  if (!sim) return screens.result();
  const empty = !sim.loading && !sim.fromScan.length && !sim.extra.length;
  return `
  <div class="top">
    <button class="back" data-go="result">‹</button>
    <div class="title">Похожие<small>${esc(slotName(sim.slot))}${sim.name ? ` · ${esc(sim.name)}` : ""}</small></div>
  </div>

  ${sim.fromScan.length ? `
    <p class="muted" style="padding:4px 20px 8px">Другие варианты этой вещи с твоего фото - от самого похожего.</p>
    <div class="items">${sim.fromScan.map(productCard).join("")}</div>` : ""}

  ${sim.extra.length ? `
    <div class="section-h"><h2>Ещё из каталога</h2></div>
    <div class="items">${sim.extra.map(productCard).join("")}</div>` : ""}

  ${sim.loading ? `<div class="loader"><div class="ring"></div><p>Ищу ещё в каталоге</p></div>` : ""}

  ${empty ? `
    <div class="empty">
      <h3>Больше похожих не нашла</h3>
      <p class="muted">Честно: других подходящих вещей в каталоге пока нет. Попробуй фото, где вещь видно крупнее.</p>
    </div>` : ""}

  <div style="padding:14px 20px 10px"><button class="btn-ghost" data-go="result">Назад к разбору</button></div>`;
};

function productCard(p) {
  return `
  <div class="item">
    <img src="${esc(p.photo_url)}" alt="">
    <div class="info">
      <div class="name">${esc(p.title)}</div>
      <div class="price">${rub(p.price)}${p.old_price ? `<s>${rub(p.old_price)}</s>` : ""}</div>
      <div class="store">${esc(p.store)}</div>
      <div class="btns"><button class="buy" data-buy="${esc(p.buy_url)}">Купить</button></div>
    </div>
  </div>`;
}

function itemCard(item, idx) {
  const p = item.products[0];
  if (!p) return "";
  // Порог совпадает с EXACT_MIN бэкенда (app/services/catalog.py): выше 80 -
  // это та самая вещь, ниже - честное «похоже». Слово понятнее процента.
  const exact = item.match_percent >= 80;
  const cls = exact ? "match high" : "match";
  const verdict = exact ? "она самая" : "похоже";
  return `
  <div class="item">
    <img src="${esc(p.photo_url)}" alt="">
    <div class="info">
      <span class="slot">${esc(slotName(item.slot))}</span>
      <span class="${cls}" title="совпадение ${item.match_percent}%">${verdict}</span>
      <div class="name">${esc(p.title)}</div>
      <div class="price">${rub(p.price)}${p.old_price ? `<s>${rub(p.old_price)}</s>` : ""}</div>
      <div class="store">${esc(p.store)}</div>
      <div class="btns">
        <button class="buy" data-buy="${esc(p.buy_url)}">Купить</button>
        <button class="alt" data-similar="${idx}">Похожие${item.products.length > 1 ? ` · ${item.products.length - 1}` : ""}</button>
      </div>
    </div>
  </div>`;
}

screens.feed = () => `
  <div class="top">
    <div class="title">Готовые образы<small>120 000 вещей из ${SHOPS.length} магазинов</small></div>
  </div>
  <div style="padding:0 20px 10px">${genderSwitch()}</div>
  <div class="filters">
    ${chip("style", null, "Все")}
    ${chip("style", "casual", "Кэжуал")}
    ${chip("style", "office", "Офис")}
    ${chip("style", "date", "Свидание")}
    ${chip("style", "smart", "Смарт")}
    ${chip("budget", 6000, "до 6 тыс")}
    ${chip("budget", 10000, "до 10 тыс")}
    ${chip("budget", 20000, "до 20 тыс")}
  </div>
  <div class="grid" id="grid"><div class="muted">Загружаю...</div></div>`;

screens.card = () => {
  const o = state.outfit;
  if (!o) return screens.feed();
  const total = o.items.reduce((s, i) => s + i.price, 0);
  return `
  <div class="top">
    <button class="back" data-go="feed">‹</button>
    <div class="title">${esc(o.title)}<small>${things(o.items.length)} в образе</small></div>
  </div>
  <div class="card-hero"><img src="${esc(o.cover_url)}" alt=""></div>
  <div class="items">
    ${o.items.map((i) => `
      <div class="item">
        <img src="${esc(i.photo_url)}" alt="">
        <div class="info">
          <span class="slot">${esc(i.slot)}</span>
          <div class="name">${esc(i.title)}</div>
          <div class="price">${rub(i.price)}</div>
          <div class="store">${esc(i.store)}</div>
          <div class="btns">
            <button class="buy" data-buy="${esc(i.buy_url)}">Купить</button>
            <button class="alt" data-fav="${esc(i.id)}" title="в избранное">♡</button>
          </div>
        </div>
      </div>`).join("")}
  </div>
  <div class="total"><div><div class="s">Весь образ</div></div><div class="p">${rub(total)}</div></div>`;
};

screens.favorites = () => {
  if (!state.favorites.length) {
    return `
    <div class="top"><div class="title">Избранное</div></div>
    <div class="empty">
      <div class="glyph">♡</div>
      <h3>Пока пусто</h3>
      <p class="muted">Жми сердечко на вещи - она сохранится сюда, чтобы вернуться и купить позже.</p>
      <div style="margin-top:18px"><button class="btn-primary" data-go="scan">Разобрать лук</button></div>
    </div>`;
  }
  return `
  <div class="top"><div class="title">Избранное<small>${state.favorites.length} вещи</small></div></div>
  <div class="items">
    ${state.favorites.map((p) => `
      <div class="item">
        <img src="${esc(p.photo_url)}" alt="">
        <div class="info">
          <div class="name">${esc(p.title)}</div>
          <div class="price">${rub(p.price)}</div>
          <div class="store">${esc(p.store)}</div>
          <div class="btns"><button class="buy" data-buy="${esc(p.buy_url)}">Купить</button></div>
        </div>
      </div>`).join("")}
  </div>`;
};

screens.profile = () => {
  const me = state.me || {};
  const sub = me.subscription || {};
  return `
  <div class="top">
    <div class="title">Профиль</div>
    <div class="avatar">${esc((me.name || "О")[0])}</div>
  </div>

  <div class="list">
    <div class="row stack">
      <div class="k">Кому подбираем</div>
      ${genderSwitch()}
    </div>
    <div class="row"><div class="k">Размер</div><div class="v">${esc(me.size || "не указан")}</div></div>
    <div class="row stack">
      <div class="k">Где искать</div>
      <div class="stores">
        ${SHOPS.map((s) => `<button class="store-chip ${(me.stores || []).includes(s) ? "on" : ""}" data-store="${esc(s)}">${esc(s)}</button>`).join("")}
      </div>
    </div>
  </div>

  <div class="section-h"><h2>Подписка</h2></div>
  ${sub.active
    ? `<div class="plan on"><div class="name">${esc(sub.plan || "Стандарт")}</div><div class="price">активна</div><p class="muted">Безлимитные разборы, 20 в сутки.</p></div>`
    : `<div class="plan">
         <div class="name">Пробный доступ</div>
         <div class="price">${sub.scans_left ?? 3} <small>разбора осталось</small></div>
         <ul><li>Без карты и регистрации</li><li>Реальные вещи с ценами</li></ul>
         <div style="margin-top:14px"><button class="btn-primary" data-go="paywall">Смотреть тарифы</button></div>
       </div>`}`;
};

screens.paywall = () => `
  <div class="top">
    <button class="back" data-go="profile">‹</button>
    <div class="title">Тарифы<small>Отменить можно в любой момент</small></div>
  </div>
  <div class="plan">
    <div class="name">Стандарт</div>
    <div class="price">199 ₽ <small>в месяц</small></div>
    <ul><li>Безлимитные разборы, 20 в сутки</li><li>Каталог 120 000 вещей, ${SHOPS.length} магазинов</li><li>Женский и мужской гардероб</li></ul>
    <div style="margin-top:14px"><button class="btn-primary" data-pay="standard">Подключить за 199 ₽</button></div>
  </div>
  <div class="plan on">
    <div class="name">Про</div>
    <div class="price">299 ₽ <small>в месяц</small></div>
    <ul><li>Всё из Стандарта</li><li>Приоритетная обработка фото</li><li>Поддержка в первую очередь</li></ul>
    <div style="margin-top:14px"><button class="btn-primary" data-pay="pro">Подключить за 299 ₽</button></div>
  </div>
  <div class="plan">
    <div class="name">Премиум</div>
    <div class="price">499 ₽ <small>в месяц</small></div>
    <ul><li>Всё из Про</li><li>Персональный подбор под запрос</li></ul>
    <div style="margin-top:14px"><button class="btn-ghost" data-pay="premium">Подключить за 499 ₽</button></div>
  </div>
  <p class="muted" style="padding:8px 20px 20px">Оплата проходит на getobraz.ru через Robokassa. Чек придёт на почту.</p>`;

/* ---------- кусочки разметки ---------- */

// Каталог вырос до 11 магазинов - на главной это видно сразу, иначе
// пользовательница не знает, где вообще ищет бот.
const SHOPS = [
  "Befree", "SELA", "ЦУМ", "Love Republic", "Finn Flare", "Incanto",
  "Street Beat", "Спортмастер", "Baon", "O'STIN", "KANZLER",
];

function shopsRow() {
  return `
  <div class="shops">
    <div class="shops-h">120 000 вещей в ${SHOPS.length} магазинах</div>
    <div class="shops-row">${SHOPS.map((s) => `<span>${esc(s)}</span>`).join("")}</div>
  </div>`;
}

function genderSwitch() {
  return `
  <div class="segmented">
    <button data-gender="women" class="${state.gender === "women" ? "on" : ""}">Себе</button>
    <button data-gender="men" class="${state.gender === "men" ? "on" : ""}">Ему</button>
  </div>`;
}

function chip(key, value, label) {
  const on = String(state.filters[key]) === String(value);
  return `<button class="chip ${on ? "on" : ""}" data-filter="${key}" data-value="${value === null ? "" : value}">${label}</button>`;
}

function lookCard(o) {
  return `
  <button class="look" data-outfit="${esc(o.id)}">
    <img src="${esc(o.cover_url)}" alt="">
    <div class="cap">${esc(o.title)}<small>от ${rub(o.price_from)}</small></div>
  </button>`;
}

/* ---------- загрузка данных ---------- */

async function loadRail() {
  const el = $("#rail");
  if (!el) return;
  const list = await API.outfits({ gender: state.gender });
  el.innerHTML = list.slice(0, 6).map(lookCard).join("") || `<p class="muted">Пока пусто</p>`;
}

async function loadGrid() {
  const el = $("#grid");
  if (!el) return;
  const list = await API.outfits({
    gender: state.gender,
    style: state.filters.style,
    budget: state.filters.budget,
  });
  el.innerHTML = list.map(lookCard).join("")
    || `<p class="muted" style="grid-column:1/-1">Под эти фильтры образов нет. Попробуй шире бюджет.</p>`;
}

// «Мои разборы» на вкладке «Разбор». Пусто - блока нет, остаётся пример.
async function loadHistory() {
  if (!$("#history")) return;
  let list = [];
  try { list = await API.scans(); } catch (_) { /* история - не повод ломать экран */ }
  const el = $("#history");
  if (!el || !list.length) return;
  el.innerHTML = `
    <div class="section-h"><h2>Мои разборы</h2></div>
    <div class="history">${list.map(historyRow).join("")}</div>`;
}

function historyRow(h) {
  return `
  <button class="history-row" data-scan-open="${esc(h.id)}">
    <img src="${esc(h.cover_url || PLACEHOLDER)}" alt="">
    <span class="h-info">
      <b>${esc(h.title)}</b>
      <small>${esc(h.date_label)} · нашла ${h.found} из ${h.items}</small>
    </span>
    ${h.total ? `<span class="h-total">${rub(h.total)}</span>` : ""}
  </button>`;
}

async function openSimilar(idx) {
  const item = state.scan && state.scan.items[idx];
  if (!item || !item.products.length) return;
  const [first, ...rest] = item.products;
  const sim = { slot: item.slot, name: item.name, fromScan: rest, extra: [], loading: rest.length < 3 };
  state.similar = sim;
  go("similar");
  if (!sim.loading) return;

  let extra = [];
  try { extra = await API.similar(first.id); } catch (_) { /* покажем то, что есть */ }
  const seen = new Set(item.products.map((p) => String(p.id)));
  sim.extra = extra.filter((p) => !seen.has(String(p.id))).slice(0, 6);
  sim.loading = false;
  // пока искали, могли уйти с экрана или открыть другую вещь
  if (state.screen === "similar" && state.similar === sim) render();
}

async function afterRender() {
  if (state.screen === "home") loadRail();
  if (state.screen === "feed") loadGrid();
  if (state.screen === "scan") loadHistory();
}

async function runScan(file) {
  state.photoUrl = file ? URL.createObjectURL(file) : null;
  state.screen = "loading";
  view().innerHTML = `<div class="screen">${screens.loading()}</div>`;
  // подсветка шагов, пока модель думает
  let step = 0;
  const timer = setInterval(() => {
    document.querySelectorAll("#steps div").forEach((d, i) => d.classList.toggle("on", i === step));
    step = (step + 1) % 3;
  }, 700);
  try {
    state.scan = await API.scan(file, state.gender);
    state.scanSaved = false;
    haptic("success");
    go("result", { silent: true });
    if (state.me && state.me.subscription && typeof state.me.subscription.scans_left === "number") {
      state.me.subscription.scans_left = Math.max(0, state.me.subscription.scans_left - 1);
    }
  } catch (e) {
    haptic("error");
    if (e && e.status === 402) {
      // бесплатные разборы кончились - это не ошибка, а место для подписки
      go("paywall", { silent: true });
    } else if (e && e.status === 422) {
      toast("Это не похоже на образ. Нужно фото с одеждой.");
      go("scan", { silent: true });
    } else {
      toast("Не получилось разобрать. Попробуй другое фото.");
      go("scan", { silent: true });
    }
    afterRender();
  } finally {
    clearInterval(timer);
  }
}

/* ---------- события ---------- */

document.addEventListener("click", async (e) => {
  const t = e.target.closest(
    "[data-go],[data-gender],[data-filter],[data-outfit],[data-buy],[data-similar]," +
    "[data-fav],[data-store],[data-pay],[data-tab],[data-size],[data-onboard-done],[data-scan-open]"
  );
  if (!t) return;

  if (t.dataset.go) { go(t.dataset.go); afterRender(); return; }
  if (t.dataset.tab) { go(t.dataset.tab); afterRender(); return; }

  if (t.dataset.gender) {
    state.gender = t.dataset.gender;
    haptic();
    render();
    afterRender();
    return;
  }

  if (t.dataset.filter) {
    const key = t.dataset.filter;
    const raw = t.dataset.value;
    const value = raw === "" ? null : (key === "budget" ? Number(raw) : raw);
    state.filters[key] = state.filters[key] === value ? null : value;
    haptic();
    render();
    loadGrid();
    return;
  }

  if (t.dataset.outfit) {
    state.outfit = await API.outfit(t.dataset.outfit);
    go("card");
    return;
  }

  if (t.dataset.buy) {
    haptic();
    if (tg && tg.openLink) tg.openLink(t.dataset.buy); else window.open(t.dataset.buy, "_blank");
    return;
  }

  if (t.dataset.similar !== undefined) {
    openSimilar(Number(t.dataset.similar));
    return;
  }

  if (t.dataset.scanOpen) {
    try {
      state.scan = await API.scanById(t.dataset.scanOpen);
    } catch (_) {
      toast("Не получилось открыть разбор");
      return;
    }
    state.scanSaved = true;
    state.photoUrl = null;
    go("result");
    return;
  }

  if (t.dataset.fav) {
    await API.favorite(t.dataset.fav);
    const item = (state.outfit ? state.outfit.items : []).find((i) => i.id === t.dataset.fav);
    if (item && !state.favorites.some((f) => f.id === item.id)) state.favorites.push(item);
    haptic("success");
    toast("Сохранила в избранное");
    return;
  }

  if (t.dataset.size) {
    state.me = state.me || {};
    state.me.size = t.dataset.size;
    await API.saveMe({ size: t.dataset.size, gender: state.gender });
    haptic();
    render();
    return;
  }

  if (t.dataset.onboardDone) {
    await API.saveMe({ size: state.me && state.me.size, gender: state.gender });
    go("home");
    afterRender();
    return;
  }

  if (t.dataset.store) {
    const s = t.dataset.store;
    const stores = state.me.stores || [];
    state.me.stores = stores.includes(s) ? stores.filter((x) => x !== s) : stores.concat(s);
    await API.saveMe({ stores: state.me.stores });
    render();
    return;
  }

  if (t.dataset.pay) {
    haptic();
    const url = "https://getobraz.ru/pay?plan=" + t.dataset.pay;
    if (tg && tg.openLink) tg.openLink(url); else window.open(url, "_blank");
    return;
  }
});

// Выбор фото: клик по кнопке открывает системный пикер.
document.addEventListener("click", (e) => {
  if (e.target && e.target.id === "pick") $("#file").click();
});
document.addEventListener("change", (e) => {
  if (e.target && e.target.id === "file" && e.target.files[0]) runScan(e.target.files[0]);
});

/* ---------- старт ---------- */

async function boot() {
  if (tg) {
    tg.ready();
    tg.expand();
    if (tg.colorScheme === "dark") document.body.classList.add("tg-dark");
    if (tg.BackButton) tg.BackButton.onClick(() => { go(BACK[state.screen] || "home"); afterRender(); });
    if (tg.setHeaderColor) { try { tg.setHeaderColor("#FFF8F6"); } catch (_) {} }
  }
  // Имя знаем сразу из initData - приветствие не ждёт ответа сервера.
  // Приём из версии Yorren, проверенной на живом Telegram.
  const tgUser = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
  state.me = { name: (tgUser && tgUser.first_name) || "красотка",
               subscription: { scans_left: 3 }, stores: [] };
  try {
    const me = await API.me();
    state.me = Object.assign(state.me, me);
    if (me.name) state.me.name = me.name;
    if (me.gender) state.gender = me.gender;
  } catch (_) {
    // профиль не пришёл - работаем с тем, что дал Telegram
  }
  if (!API.isLive()) showDemoBadge();
  // Размер не указан - проводим через короткий онбординг, но только один раз.
  state.screen = state.me && state.me.size ? "home" : "onboarding";
  render();
  afterRender();
}

function showDemoBadge() {
  const badge = document.createElement("div");
  badge.className = "demo-badge";
  badge.textContent = "демо-данные";
  document.body.appendChild(badge);
}

boot();
