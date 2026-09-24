"""Offline tests for the IDX big-cap / swing modules."""

import json
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from pulse.core.idx.benchmark import ex_hsc_returns
from pulse.core.idx.hsc import is_hsc, load_hsc
from pulse.core.idx.ownership import parse_ff_bei, parse_ksei
from pulse.core.idx.prices import WIB, last_complete_session
from pulse.core.idx.summary import COLUMN_MAP, parse_summary_file
from pulse.core.idx.swing import (
    SwingParams,
    backtest,
    classify,
    round_down_tick,
    round_up_tick,
    tick_size,
)
from pulse.core.idx.universe import UniverseRules, exclusion_reason


def test_hsc_list():
    as_of, tickers = load_hsc()
    assert as_of == "2026-09-24"
    assert len(tickers) == 59
    assert is_hsc("byan") and is_hsc("MGLV")
    assert not is_hsc("BBCA")


@pytest.mark.parametrize(
    "price,tick",
    [
        (50, 1),
        (199, 1),
        (200, 2),
        (499, 2),
        (500, 5),
        (1995, 5),
        (2000, 10),
        (4990, 10),
        (5000, 25),
    ],
)
def test_tick_size(price, tick):
    assert tick_size(price) == tick


def test_tick_rounding():
    assert round_down_tick(3083) == 3080
    assert round_up_tick(3083) == 3090
    assert round_down_tick(18317) == 18300
    assert round_up_tick(191.2) == 192


def test_ex_hsc_removes_hsc_contribution():
    idx = pd.date_range("2026-01-01", periods=2)
    # Two stocks, equal cap. HSC stock +10%, other +0%. IHSG therefore +5%.
    ret = pd.DataFrame({"HSC1": [0.10, 0.0], "OTHER": [0.0, 0.02]}, index=idx)
    mcap = pd.DataFrame({"HSC1": [100.0, 100.0], "OTHER": [100.0, 100.0]}, index=idx)
    ihsg = pd.Series([0.05, 0.01], index=idx)
    r_ex, w = ex_hsc_returns(ihsg, ret, mcap, {"HSC1"})
    assert w.iloc[0] == pytest.approx(0.5)
    assert r_ex.iloc[0] == pytest.approx(0.0)  # only the non-HSC stock remains
    assert r_ex.iloc[1] == pytest.approx(0.02)


def test_parse_summary_file(tmp_path):
    cols = {v: k for k, v in COLUMN_MAP.items()}
    row = {c: 0 for c in COLUMN_MAP}
    row.update(
        {
            cols["code"]: " bbca ",
            cols["name"]: "Bank Central Asia Tbk.",
            cols["close"]: 6300,
            cols["listed_shares"]: 1_000,
            cols["foreign_buy"]: 70,
            cols["foreign_sell"]: 50,
            cols["last_trade_date"]: "23 Sep 2026",
        }
    )
    path = tmp_path / "Ringkasan Saham-20260923.xlsx"
    pd.DataFrame([row]).to_excel(path, index=False)

    df = parse_summary_file(path)
    r = df.iloc[0]
    assert r.date == pd.Timestamp("2026-09-23")
    assert r.code == "BBCA"
    assert r.market_cap == 6_300_000
    assert r.foreign_net == 20


def test_parse_ownership_pages():
    ff_rows = [
        {
            "n": 1,
            "k": "BYAN",
            "c": "Bayan",
            "p": "Utama",
            "m": 1,
            "ms": "1",
            "j": 5000,
            "js": "5.000",
            "f": 21.3,
            "fs": "21,3%",
            "w": 15.0,
            "ws": "15%",
            "b": "Telah Memenuhi",
        }
    ]
    ff_html = f'<script id="rawData" type="application/json">{json.dumps(ff_rows)}</script>'
    ff = parse_ff_bei(ff_html)
    assert ff.loc[0, "ff_bei"] == 21.3 and ff.loc[0, "ff_status"] == "Telah Memenuhi"

    groups = [
        {
            "share_code": "BYAN",
            "freeFloat": 1.51,
            "cr1": 40.25,
            "holderCount": 10,
            "ownershipType": "Oligopoli",
            "sector": "Energy",
            "industry": "Coal",
        }
    ]
    payload = json.dumps([1, '6:{"stockGroups":' + json.dumps(groups) + ',"x":1}'])
    ksei_html = (
        f"<script>self.__next_f.push({payload})</script>"
        '<script>{"currentDate":"2026-08-31"}</script>'
    )
    ksei, snap = parse_ksei(ksei_html)
    assert ksei.loc[0, "ff_ksei"] == pytest.approx(1.51)
    assert snap == "2026-08-31"


def test_exclusion_reason():
    rules = UniverseRules()
    hsc = frozenset({"BYAN"})
    base = {"ff_status": "Telah Memenuhi", "ff_ksei": 40.0, "avg_value_bn": 100.0}
    assert exclusion_reason(pd.Series({**base, "code": "BBCA"}), rules, hsc) == ""
    assert exclusion_reason(pd.Series({**base, "code": "BYAN"}), rules, hsc) == "HSC"
    assert "free float" in exclusion_reason(
        pd.Series({**base, "code": "X", "ff_ksei": 12.3}), rules, hsc
    )
    assert "likuiditas" in exclusion_reason(
        pd.Series({**base, "code": "X", "avg_value_bn": 1.0}), rules, hsc
    )
    assert (
        exclusion_reason(
            pd.Series({**base, "code": "X", "ff_status": "Voluntary Delisting"}), rules, hsc
        )
        == "delisting"
    )


def test_classify_setups():
    base = dict(
        close=110.0,
        ma20=105.0,
        ma50=100.0,
        ma100=90.0,
        atr=3.0,
        rs13=5.0,
        to_hh55=-1.0,
        vol_ratio=1.2,
        rsi=60.0,
    )
    assert classify(pd.Series(base)) == "BREAKOUT"
    assert (
        classify(pd.Series({**base, "to_hh55": -10.0, "close": 106.0, "rsi": 45.0})) == "PULLBACK"
    )
    assert classify(pd.Series({**base, "to_hh55": -10.0})) == "TREND"
    assert classify(pd.Series({**base, "close": 95.0, "rs13": -3.0})) == "HINDARI"


def test_screen_marks_untraded_stock_inactive():
    from pulse.core.idx.swing import screen

    dates = pd.bdate_range("2026-01-01", periods=5)
    frame = lambda a, b: pd.DataFrame({"AAA": a, "BBB": b}, index=dates)  # noqa: E731
    ind = {
        "close": frame(110.0, 110.0),
        "ma20": frame(105.0, 105.0),
        "ma50": frame(100.0, 100.0),
        "ma100": frame(90.0, 90.0),
        "atr": frame(3.0, 3.0),
        "hh55": frame(111.0, 111.0),
        "vol_ratio": frame(1.2, 1.2),
        "rsi": frame(60.0, 60.0),
        "rs13": frame(0.1, 0.1),
        "rs4": frame(0.05, 0.05),
        "volume": frame(1e6, [1e6] * 4 + [np.nan]),
        "market_ok": pd.Series(True, index=dates),
    }
    snap = screen(ind, ["AAA", "BBB"], SwingParams())
    assert snap.at["AAA", "setup"] == "BREAKOUT"
    assert snap.at["BBB", "setup"] == "TIDAK AKTIF"  # mis. SINI 24 Sep 2026: order book kosong


def test_last_complete_session():
    # Thursday 14:02 WIB, market still open -> Wednesday
    assert str(last_complete_session(datetime(2026, 9, 24, 14, 2, tzinfo=WIB))) == "2026-09-23"
    # Thursday after close -> Thursday
    assert str(last_complete_session(datetime(2026, 9, 24, 17, 0, tzinfo=WIB))) == "2026-09-24"
    # Monday morning -> previous Friday
    assert str(last_complete_session(datetime(2026, 9, 28, 9, 0, tzinfo=WIB))) == "2026-09-25"


def test_backtest_trending_stock_is_bought_and_fees_applied():
    dates = pd.bdate_range("2023-01-02", periods=260)
    price = pd.Series(np.linspace(1000, 2000, len(dates)), index=dates)
    close = pd.DataFrame({"AAA": price})
    ind = {
        "close": close,
        "open": close,
        "ma20": close.rolling(20).mean(),
        "ma50": close.rolling(50).mean(),
        "ma100": close.rolling(100).mean(),
        "atr": close * 0 + 20,
        "hh55": close.rolling(55).max(),
        "vol_ratio": close * 0 + 1.5,
        "value20": close * 0 + 1e12,
        "rs13": close * 0 + 0.1,
        "rs4": close * 0 + 0.05,
        "rsi": close * 0 + 60,
        "market_ok": pd.Series(True, index=dates),
    }
    mcap = close * 1e9
    bench = pd.DataFrame({"IHSG": price, "IHSG_exHSC": price}, index=dates)
    res = backtest(ind, mcap, bench, SwingParams(slots=1), start="2023-07-03")
    assert len(res.trades) >= 1
    assert res.equity.iloc[-1] > 1.0
    # time exit after max_hold, fees make return slightly below raw price change
    t = res.trades.iloc[0]
    assert t.reason == "waktu"
    assert t.ret < t.exit / t.entry - 1
