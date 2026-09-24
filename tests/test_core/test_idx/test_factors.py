"""Offline tests for per-stock factors and dashboard rendering."""

import json

import numpy as np
import pandas as pd
import pytest

from pulse.core.idx import factors
from pulse.core.idx.dashboard import render


def _series(values, name="AAA"):
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)), name=name)


def test_stage_markup_and_markdown():
    up = _series(np.linspace(1000, 2000, 300))
    down = _series(np.linspace(2000, 1000, 300))
    assert factors.stage_with_age(up)[0] == factors.MARKUP
    assert factors.stage_with_age(down)[0] == factors.MARKDOWN


def test_stage_v_reversal_is_accumulation_not_distribution():
    # Long decline, then a sharp rally above a still-falling MA150 (like SINI Sep 2026)
    values = np.concatenate([np.linspace(2000, 800, 260), np.linspace(800, 1600, 20)])
    stage, _, _ = factors.stage_with_age(_series(values))
    assert stage == factors.AKUMULASI


def test_debounce_ignores_short_flips():
    s = pd.Series(["A"] * 10 + ["B"] * 3 + ["A"] * 5 + ["B"] * 6)
    out = factors.debounce(s, n=5)
    assert (out.iloc[:18] == "A").all()
    assert out.iloc[-1] == "B"


def test_cmf_bounds_and_sign():
    idx = pd.bdate_range("2024-01-01", periods=30)
    high = pd.DataFrame({"A": 110.0, "B": 110.0}, index=idx)
    low = pd.DataFrame({"A": 100.0, "B": 100.0}, index=idx)
    close = pd.DataFrame({"A": 110.0, "B": 100.0}, index=idx)  # A closes at high, B at low
    vol = pd.DataFrame({"A": 1e6, "B": 1e6}, index=idx)
    last = factors.cmf(high, low, close, vol).iloc[-1]
    assert last["A"] == pytest.approx(1.0)
    assert last["B"] == pytest.approx(-1.0)


def test_foreign_factors_convert_shares_to_rupiah():
    dates = pd.bdate_range("2026-09-01", periods=6)
    hist = pd.DataFrame(
        {
            "date": dates,
            "code": "BBCA",
            "close": 6000.0,
            "foreign_net": 1_000_000,  # lembar
            "value": 60e9,
            "frequency": 10_000,
            "nonreg_value": 0.0,
        }
    )
    ff = factors.foreign_factors(hist, ["BBCA", "XXXX"])
    assert ff.loc["BBCA", "days"] == 6
    assert ff.loc["BBCA", "net_today_bn"] == pytest.approx(6.0)  # 1 jt lembar x Rp 6.000
    assert ff.loc["BBCA", "net20_pct"] == pytest.approx(10.0)
    assert ff.loc["BBCA", "big_lot"] == pytest.approx(1.0)
    assert ff.loc["XXXX", "days"] == 0


def test_big_lot_label_uses_price_direction():
    assert factors.big_lot_label(2.0, 1.5) == "bull"
    assert factors.big_lot_label(247.0, -1.0) == "bear"  # CARE 23 Sep 2026: blok besar, harga turun
    assert factors.big_lot_label(1.1, 3.0) == "neutral"
    assert factors.big_lot_label(float("nan"), 1.0) == "na"


def test_nonreg_share_of_total():
    dates = pd.bdate_range("2026-09-01", periods=6)
    hist = pd.DataFrame(
        {
            "date": dates,
            "code": "CARE",
            "close": 400.0,
            "foreign_net": 0,
            "value": 1e9,
            "frequency": 100,
            "nonreg_value": 3e9,  # nego jauh lebih besar dari reguler
        }
    )
    assert factors.foreign_factors(hist, ["CARE"]).loc["CARE", "nonreg_pct"] == pytest.approx(75.0)


def test_labels():
    assert factors.label("stage", factors.MARKUP) == "bull"
    assert factors.label("rs13", -6) == "bear"
    assert factors.label("cmf", 0.01) == "neutral"
    assert factors.label("foreign", None) == "na"
    assert factors.label("foreign", float("nan")) == "na"


def test_sector_rotation_quadrants():
    idx = pd.bdate_range("2025-01-01", periods=200)
    bench = pd.Series(np.linspace(100, 110, 200), index=idx)
    close = pd.DataFrame(
        {
            "A1": np.linspace(100, 200, 200),
            "A2": np.linspace(100, 190, 200),
            "B1": np.linspace(100, 60, 200),
            "B2": np.linspace(100, 65, 200),
        },
        index=idx,
    )
    sectors = pd.Series({"A1": "Strong", "A2": "Strong", "B1": "Weak", "B2": "Weak"})
    out = {s["sector"]: s for s in factors.sector_rotation(close, sectors, bench)}
    assert out["Strong"]["trail"][-1][0] > 100
    assert out["Weak"]["trail"][-1][0] < 100


def test_render_embeds_json_safely():
    payload = {"meta": {"note": "</script><b>x</b>"}, "rows": []}
    html = render(payload)
    assert "/*__PULSE_DATA__*/null" not in html
    assert "</script><b>" not in html  # cannot break out of the script tag
    start = html.index("const DATA = ") + len("const DATA = ")
    end = html.index(";\n", start)
    assert json.loads(html[start:end].replace("<\\/", "</")) == payload
