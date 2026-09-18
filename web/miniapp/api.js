/* Слой данных мини-аппа «Образ».
 *
 * Один контракт из docs/miniapp-brief-2026-09-03.md, две реализации:
 * MOCK - заглушки для вёрстки, LIVE - реальные эндпоинты бэкенда.
 * Переключение одной строкой ниже, больше нигде в коде правок не нужно.
 */

const API = (() => {
  // "auto" - пробуем живой бэкенд, при неудаче падаем на заглушки и говорим
  // об этом в интерфейсе. Так вёрстку можно открыть в обычном браузере, а в
  // Telegram она сама работает на реальных данных.
  const MODE = "auto";                 // auto | live | mock
  const BASE = "/api";                 // мини-апп раздаётся с того же домена
  const LATENCY = 260;                 // имитация сети, чтобы лоадеры были видны

  const tg = window.Telegram && window.Telegram.WebApp;
  let live = MODE === "live";
  let probed = MODE !== "auto";

  /* ---------- реальные запросы ---------- */

  class ApiError extends Error {
    constructor(status, body) {
      super("HTTP " + status);
      this.status = status;
      this.body = body || {};
    }
  }

  async function request(path, options = {}) {
    const headers = Object.assign({}, options.headers || {});
    // Авторизация мини-аппа: сырой initData, сервер проверяет подпись сам.
    if (tg && tg.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    if (options.json !== undefined) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(options.json);
      delete options.json;
    }
    const resp = await fetch(BASE + path, Object.assign({}, options, { headers }));
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new ApiError(resp.status, body);
    }
    return resp.json();
  }

  // Один раз на старте выясняем, отвечает ли бэкенд. Ошибка сети или 401 -
  // работаем на заглушках: лучше показать демо, чем пустой экран.
  async function probe() {
    if (probed) return live;
    probed = true;
    if (!tg || !tg.initData) {
      live = false;
      return live;
    }
    try {
      await request("/me");
      live = true;
    } catch (_) {
      live = false;
    }
    return live;
  }

  async function pick(liveCall, mockCall) {
    await probe();
    if (!live) return mockCall();
    try {
      return await liveCall();
    } catch (e) {
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) throw e;
      // сеть или пятисотка - показываем демо, чтобы экран не остался пустым
      live = false;
      return mockCall();
    }
  }

  /* ---------- заглушки ---------- */

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const PHOTO = {
    look_w: "/app/img/hero-walk.jpg",
    look_m: "/app/img/app-wardrobe.jpg",
    shirt: "/app/img/item-shirt.jpg",
    pants: "/app/img/item-pants.jpg",
    sneakers: "/app/img/item-sneakers.jpg",
    bag: "/app/img/item-bag.jpg",
    coat: "/app/img/item-coat.jpg",
    polo: "/app/img/item-loafers.jpg",
    feed1: "/app/img/flatlay-women.jpg",
    feed2: "/app/img/flatlay-men.jpg",
    feed3: "/app/img/detail-bag.jpg",
    feed4: "/app/img/app-scan.jpg",
  };

  const product = (id, title, price, old_price, store, photo) => ({
    id, title, price, old_price, store, photo_url: photo,
    buy_url: "https://getobraz.ru/go/" + id,
  });

  const MOCK_SCAN_W = {
    vibe: "Городской шик - спокойные тона, чистые линии, база на каждый день",
    gender: "women",
    items: [
      {
        slot: "Верх", name: "Рубашка оверсайз из фактурной ткани", color: "молочный", match_percent: 94,
        products: [
          product("w-101", "Рубашка оверсайз хлопковая", 1999, 2999, "Befree", PHOTO.shirt),
          product("w-102", "Рубашка свободного кроя", 2490, null, "SELA", PHOTO.shirt),
        ],
      },
      {
        slot: "Низ", name: "Брюки широкие из тенсела", color: "бежевый", match_percent: 91,
        products: [
          product("w-201", "Брюки широкие палаццо", 2299, 3499, "SELA", PHOTO.pants),
          product("w-202", "Брюки прямые с защипами", 3990, null, "Love Republic", PHOTO.pants),
        ],
      },
      {
        slot: "Обувь", name: "Кроссовки кожаные белые", color: "белый", match_percent: 88,
        products: [product("w-301", "Кроссовки кожаные минималистичные", 6490, null, "ЦУМ", PHOTO.sneakers)],
      },
      {
        slot: "Сумка", name: "Сумка-багет из гладкой кожи", color: "карамель", match_percent: 82,
        products: [product("w-401", "Сумка-багет на короткой ручке", 3790, 4990, "Befree", PHOTO.bag)],
      },
    ],
  };

  const MOCK_SCAN_M = {
    vibe: "Олд-мани в будни - мягкие фактуры, спокойная гамма, ничего лишнего",
    gender: "men",
    items: [
      {
        slot: "Верх", name: "Поло трикотажное мелкой вязки", color: "оливковый", match_percent: 93,
        products: [product("m-101", "Поло трикотажное короткий рукав", 3490, 4290, "KANZLER", PHOTO.polo)],
      },
      {
        slot: "Верхняя одежда", name: "Пальто однобортное без подкладки", color: "песочный", match_percent: 87,
        products: [product("m-201", "Пальто прямого кроя", 12900, null, "KANZLER", PHOTO.coat)],
      },
      {
        slot: "Низ", name: "Брюки со стрелкой из костюмной ткани", color: "бежевый", match_percent: 90,
        products: [product("m-301", "Брюки классические зауженные", 4990, null, "KANZLER", PHOTO.pants)],
      },
    ],
  };

  const MOCK_OUTFITS = [
    { id: "o1", title: "Городской шик", cover_url: PHOTO.feed1, price_from: 6730, style: "casual", gender: "women" },
    { id: "o2", title: "Свидание", cover_url: PHOTO.look_w, price_from: 8900, style: "date", gender: "women" },
    { id: "o3", title: "Офис", cover_url: PHOTO.feed2, price_from: 12400, style: "office", gender: "women" },
    { id: "o4", title: "Выходные", cover_url: PHOTO.feed3, price_from: 5480, style: "casual", gender: "women" },
    { id: "o5", title: "Смарт-кэжуал", cover_url: PHOTO.look_m, price_from: 14300, style: "smart", gender: "men" },
    { id: "o6", title: "База на неделю", cover_url: PHOTO.feed4, price_from: 9900, style: "casual", gender: "men" },
  ];

  const MOCK_ME = {
    name: "Ника",
    gender: "women",
    size: "M",
    stores: ["Befree", "SELA", "ЦУМ", "Love Republic"],
    subscription: { active: false, plan: null, scans_left: 3 },
  };

  // Демо-история: разборы, сделанные в этой вкладке, как их вернул бы сервер.
  const mockHistory = [];
  const dateLabel = (d) =>
    `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}, ` +
    `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;

  const mocks = {
    async scan(_file, gender) {
      await sleep(1800);
      const base = gender === "men" ? MOCK_SCAN_M : MOCK_SCAN_W;
      const saved = Object.assign(JSON.parse(JSON.stringify(base)), {
        id: mockHistory.length + 1,
        date_label: dateLabel(new Date()),
      });
      mockHistory.unshift(saved);
      return saved;
    },
    async scans() {
      await sleep(LATENCY);
      return mockHistory.map((s) => {
        const firsts = s.items.filter((i) => i.products.length).map((i) => i.products[0]);
        return {
          id: s.id, date_label: s.date_label, title: s.vibe.split(" - ")[0],
          items: s.items.length, found: firsts.length,
          cover_url: firsts.length ? firsts[0].photo_url : null,
          total: firsts.reduce((sum, p) => sum + p.price, 0),
        };
      });
    },
    async scanById(id) {
      await sleep(LATENCY);
      const found = mockHistory.find((s) => String(s.id) === String(id));
      if (!found) throw new ApiError(404, { detail: "Разбор не найден" });
      return JSON.parse(JSON.stringify(found));
    },
    async outfits(params) {
      await sleep(LATENCY);
      return MOCK_OUTFITS.filter((o) => {
        if (params.gender && o.gender !== params.gender) return false;
        if (params.style && o.style !== params.style) return false;
        if (params.budget && o.price_from > params.budget) return false;
        return true;
      });
    },
    async outfit(id) {
      await sleep(LATENCY);
      const head = MOCK_OUTFITS.find((o) => o.id === id) || MOCK_OUTFITS[0];
      const src = head.gender === "men" ? MOCK_SCAN_M : MOCK_SCAN_W;
      return {
        id: head.id, title: head.title, cover_url: head.cover_url,
        items: src.items.map((i) => Object.assign({ slot: i.slot }, i.products[0])),
      };
    },
    async similar(productId) {
      await sleep(LATENCY);
      // как бэкенд: похожие той же вещи, а не весь образ подряд
      const pool = String(productId).startsWith("m-") ? MOCK_SCAN_M : MOCK_SCAN_W;
      const item = pool.items.find((i) => i.products.some((p) => p.id === productId));
      return item ? item.products.filter((p) => p.id !== productId) : [];
    },
    async favorite(productId) { await sleep(120); return { ok: true, id: productId }; },
    async me() { await sleep(LATENCY); return JSON.parse(JSON.stringify(MOCK_ME)); },
    async saveMe(patch) { await sleep(LATENCY); return Object.assign(MOCK_ME, patch); },
  };

  /* ---------- публичный интерфейс ---------- */

  return {
    ApiError,
    isLive: () => live,

    // POST /api/scan  - multipart photo
    scan(file, gender) {
      return pick(
        () => {
          const body = new FormData();
          body.append("photo", file);
          return request("/scan", { method: "POST", body });
        },
        () => mocks.scan(file, gender),
      );
    },

    // GET /api/scans - мои разборы, свежие сверху
    scans() { return pick(() => request("/scans"), () => mocks.scans()); },

    // GET /api/scans/{id} - сохранённый разбор целиком, в контракте POST /api/scan
    scanById(id) {
      return pick(
        () => request("/scans/" + encodeURIComponent(id)),
        () => mocks.scanById(id),
      );
    },

    // GET /api/outfits?style=&budget=&gender=
    outfits(params = {}) {
      return pick(
        () => {
          const q = new URLSearchParams();
          Object.entries(params).forEach(([k, v]) => { if (v) q.set(k, v); });
          return request("/outfits?" + q.toString());
        },
        () => mocks.outfits(params),
      );
    },

    // GET /api/outfits/{id}
    outfit(id) {
      return pick(() => request("/outfits/" + encodeURIComponent(id)), () => mocks.outfit(id));
    },

    // GET /api/similar/{product_id}
    similar(productId) {
      return pick(
        () => request("/similar/" + encodeURIComponent(productId)),
        () => mocks.similar(productId),
      );
    },

    // POST /api/favorites/{product_id}
    favorite(productId) {
      return pick(
        () => request("/favorites/" + encodeURIComponent(productId), { method: "POST" }),
        () => mocks.favorite(productId),
      );
    },

    // GET /api/me
    me() { return pick(() => request("/me"), () => mocks.me()); },

    // POST /api/me
    saveMe(patch) {
      return pick(() => request("/me", { method: "POST", json: patch }), () => mocks.saveMe(patch));
    },
  };
})();
