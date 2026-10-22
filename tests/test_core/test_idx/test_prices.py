"""Offline tests for the price cache: rate limits must never wipe good data."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from pulse.core.idx import prices


def _yahoo_frame(symbols, dates, base=100.0):
    cols = pd.MultiIndex.from_product(
        [["Open", "High", "Low", "Close", "Adj Close", "Volume"], symbols]
    )
    data = np.full((len(dates), len(cols)), base)
    return pd.DataFrame(data, index=pd.DatetimeIndex(dates), columns=cols)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(prices, "PRICE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(prices, "last_complete_session", lambda now=None: date(2026, 10, 8))
    monkeypatch.setattr(prices._time, "sleep", lambda s: None)
    calls = []

    def install(fn):
        def fake(symbols, start, **kw):
            calls.append((list(symbols), start))
            return fn(symbols, start)

        monkeypatch.setattr(prices.yf, "download", fake)

    return install, calls


def _seed_cache(tickers, last="2026-09-25"):
    dates = pd.bdate_range("2026-09-01", last)
    panel = {f: pd.DataFrame(100.0, index=dates, columns=tickers) for f in prices.FIELDS}
    prices._save_cache("t", panel)
    return panel


def test_rate_limited_download_keeps_cache(env):
    install, _ = env
    install(lambda symbols, start: pd.DataFrame())  # Yahoo 429 -> kosong
    _seed_cache(["BBCA", "^JKSE"])
    out = prices.fetch_panel(["BBCA", "^JKSE"], name="t")
    assert out["close"]["BBCA"].notna().all() and len(out["close"]) > 0  # pakai cache lama
    assert len(prices._load_cache("t")["close"]) > 0  # cache tidak tertimpa data kosong


def test_rate_limited_without_cache_raises(env):
    install, _ = env
    install(lambda symbols, start: pd.DataFrame())
    with pytest.raises(prices.PriceDownloadError):
        prices.fetch_panel(["BBCA"], name="t")


def test_incremental_update_only_downloads_recent_days_and_new_tickers(env):
    install, calls = env
    _seed_cache(["BBCA"], last="2026-09-25")

    def fake(symbols, start):
        dates = pd.bdate_range(start, "2026-10-08")
        return _yahoo_frame(symbols, dates, base=200.0)

    install(fake)
    out = prices.fetch_panel(["BBCA", "ASII"], start="2023-01-01", name="t")
    starts = {tuple(s): st for s, st in calls}
    assert starts[("BBCA.JK",)] == "2026-09-15"  # 10 hari tumpang tindih, bukan dari 2023
    assert starts[("ASII.JK",)] == "2023-01-01"  # ticker baru: histori penuh
    assert out["close"].index.max() == pd.Timestamp("2026-10-08")
    assert out["close"].at[pd.Timestamp("2026-09-01"), "BBCA"] == 100.0  # histori lama tetap
    assert out["close"].at[pd.Timestamp("2026-10-08"), "BBCA"] == 200.0


def test_current_cache_makes_no_request(env):
    install, calls = env
    install(lambda symbols, start: pd.DataFrame())
    _seed_cache(["BBCA"], last="2026-10-08")
    prices.fetch_panel(["BBCA"], name="t")
    assert calls == []
