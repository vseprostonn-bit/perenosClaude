from app.services.pricing import PRICES, price_bucket, price_for


def test_bucket_deterministic() -> None:
    assert price_bucket(123456) == price_bucket(123456)
    assert price_for(123456) == price_for(123456)


def test_all_prices_reachable() -> None:
    got = {price_for(tg_id) for tg_id in range(100)}
    assert got == set(PRICES)


def test_price_in_grid() -> None:
    for tg_id in (1, 999999999, 5555555555):
        assert price_for(tg_id) in PRICES
