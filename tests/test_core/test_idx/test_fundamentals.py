"""Offline tests for XBRL-derived fundamentals and disclosure filtering."""

from datetime import date

import pytest

from pulse.core.idx.fundamentals import compute, recent_events


def _item(currency="Rupiah / IDR", industry="C31. Multi-sector Holdings", **over):
    latest = {
        "year": 2026,
        "period": "TW2",
        "currency": currency,
        "industry": industry,
        "type": "Tidak Diaudit / Unaudit",
        "end": "2026-06-30",
        "instant": {
            "Equity": 1200.0,
            "EquityAttributableToEquityOwnersOfParentEntity": 1000.0,
            "Liabilities": 500.0,
        },
        "current": {
            "ProfitLossAttributableToParentEntity": 60.0,
            "SalesAndRevenue": 600.0,
            "NetCashFlowsReceivedFromUsedInOperatingActivities": 70.0,
        },
        "prior": {
            "ProfitLossAttributableToParentEntity": 50.0,
            "SalesAndRevenue": 500.0,
            "NetCashFlowsReceivedFromUsedInOperatingActivities": 40.0,
        },
    }
    fy = {
        "current": {
            "ProfitLossAttributableToParentEntity": 100.0,
            "SalesAndRevenue": 1000.0,
            "NetCashFlowsReceivedFromUsedInOperatingActivities": 90.0,
        }
    }
    latest.update(over)
    return {"latest": latest, "fy": fy}


def test_ttm_valuation_idr():
    m = compute(_item(), market_cap=1100.0, fx_usd=16_000)
    # TTM laba = 100 + 60 - 50 = 110 -> PE 10, ROE 11%, PBV 1.1
    assert m["pe"] == pytest.approx(10.0)
    assert m["roe"] == pytest.approx(11.0)
    assert m["pbv"] == pytest.approx(1.1)
    assert m["ni_growth"] == pytest.approx(20.0)
    assert m["rev_growth"] == pytest.approx(20.0)
    assert m["der"] == pytest.approx(0.5)
    assert m["ocf_ni"] == pytest.approx(120 / 110)
    assert m["currency"] == "IDR" and not m["flags"]


def test_usd_report_converted():
    m = compute(_item(currency="Dollar Amerika / USD"), market_cap=110.0 * 16_000, fx_usd=16_000)
    assert m["currency"] == "USD"
    assert m["pe"] == pytest.approx(1.0)
    assert m["roe"] == pytest.approx(11.0)  # rasio tidak terpengaruh kurs


def test_bank_uses_interest_income_and_skips_der():
    item = _item(industry="G11. Banks")
    item["latest"]["current"] = {
        "ProfitLossAttributableToParentEntity": 60.0,
        "InterestIncome": 300.0,
    }
    item["latest"]["prior"] = {
        "ProfitLossAttributableToParentEntity": 50.0,
        "InterestIncome": 250.0,
    }
    m = compute(item, market_cap=1100.0, fx_usd=16_000)
    assert m["bank"] and m["der"] is None and m["ocf_ni"] is None
    assert m["rev_growth"] == pytest.approx(20.0)


def test_flags_for_falling_profit_and_losses():
    item = _item()
    item["latest"]["current"]["ProfitLossAttributableToParentEntity"] = 20.0  # -60% YoY
    m = compute(item, market_cap=1000.0, fx_usd=16_000)
    assert any("turun" in f for f in m["flags"])
    item["fy"]["current"]["ProfitLossAttributableToParentEntity"] = -100.0
    m = compute(item, market_cap=1000.0, fx_usd=16_000)
    assert m["pe"] is None and "Rugi (TTM)" in m["flags"]


def test_profit_not_backed_by_cash_flagged():
    item = _item()
    for part in ("current", "prior"):
        item["latest"][part]["NetCashFlowsReceivedFromUsedInOperatingActivities"] = 1.0
    item["fy"]["current"]["NetCashFlowsReceivedFromUsedInOperatingActivities"] = 2.0
    m = compute(item, market_cap=1000.0, fx_usd=16_000)
    assert any("belum jadi kas" in f for f in m["flags"])


def test_negative_equity_flagged_not_ratioed():
    # SINI TW2 2026: ekuitas induk negatif walau laba YTD positif
    item = _item()
    item["latest"]["instant"].update(
        {"EquityAttributableToEquityOwnersOfParentEntity": -125.0, "Equity": -53.0}
    )
    m = compute(item, market_cap=1000.0, fx_usd=16_000)
    assert "Ekuitas negatif" in m["flags"]
    assert m["der"] is None and m["pbv"] is None and m["roe"] is None


def test_recent_events_window_and_order():
    raw = {
        "announcements": {
            "BBCA": [
                {
                    "date": "2026-09-20",
                    "category": "dividen",
                    "title": "Jadwal Dividen",
                    "url": None,
                },
                {"date": "2026-06-01", "category": "rups", "title": "RUPS", "url": None},
            ],
            "ADRO": [
                {"date": "2026-09-22", "category": "buyback", "title": "Buyback", "url": None}
            ],
        }
    }
    ev = recent_events(raw, days=30, today=date(2026, 9, 24))
    assert [e["code"] for e in ev] == ["ADRO", "BBCA"]
    assert ev[0]["label"] == "Buyback"
