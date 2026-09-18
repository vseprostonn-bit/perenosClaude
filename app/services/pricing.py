"""A/B цен: бакет детерминирован по tg_id - одна девочка всегда видит одну цену."""

PRICES: tuple[int, ...] = (199, 299, 499)


def price_bucket(tg_id: int) -> int:
    return tg_id % len(PRICES)


def price_for(tg_id: int) -> int:
    return PRICES[price_bucket(tg_id)]
