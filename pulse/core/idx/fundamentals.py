"""Fundamentals & corporate disclosures from idx.co.id (XBRL + announcements).

Data is collected in a normal browser with ``scripts/idx_browser_extract.js`` (idx.co.id
blocks non-browser clients) and saved as ``data/fundamentals/pulse_idx_YYYYMMDD.json``.

Valuation uses trailing twelve months (TTM):
    TTM = last full year (audited) + current YTD - same YTD last year
Reports in USD are converted with the current USD/IDR rate so PE/PBV compare with IDR prices.
Fundamentals are context for swing trades, not a timing signal.
"""

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

from pulse.core.idx import DATA_DIR
from pulse.utils.logger import get_logger

log = get_logger(__name__)

FUND_DIR = DATA_DIR / "fundamentals"
NI = "ProfitLossAttributableToParentEntity"
OCF = "NetCashFlowsReceivedFromUsedInOperatingActivities"

EVENT_LABELS = {
    "dividen": "Dividen",
    "rups": "RUPS",
    "buyback": "Buyback",
    "rights_issue": "Rights issue / PMTHMETD",
    "transaksi_material": "Transaksi material / akuisisi",
    "afiliasi": "Transaksi afiliasi",
    "kepemilikan": "Perubahan kepemilikan / pengendali",
    "tender_offer": "Tender offer",
    "penjelasan_bursa": "Penjelasan ke Bursa",
    "suspensi": "Suspensi",
    "stock_split": "Stock split",
    "laporan_keuangan": "Laporan keuangan",
}


def latest_file() -> Path | None:
    files = sorted(FUND_DIR.glob("pulse_idx_*.json"))
    return files[-1] if files else None


def load_raw(path: Path | None = None) -> dict | None:
    path = path or latest_file()
    if path is None:
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def usd_idr() -> float:
    """Latest USD/IDR close (Yahoo), fallback to a conservative constant if offline."""
    try:
        s = yf.download("USDIDR=X", period="10d", progress=False, auto_adjust=False)["Close"]
        return float(s.dropna().iloc[-1].squeeze())
    except Exception as e:  # noqa: BLE001
        log.warning(f"Kurs USD/IDR gagal diambil ({e}); pakai 16.500")
        return 16_500.0


def _get(d: dict | None, key: str):
    v = (d or {}).get(key)
    return None if v is None else float(v)


def _ttm(latest: dict, fy: dict | None, key: str):
    cur = _get(latest.get("current"), key)
    if latest.get("period") == "AUDIT":
        return cur
    prior = _get(latest.get("prior"), key)
    full = _get((fy or {}).get("current"), key)
    if None in (cur, prior, full):
        return None
    return full + cur - prior


def _growth(cur, prior):
    if cur is None or prior is None or prior <= 0:
        return None
    return (cur / prior - 1) * 100


def is_bank(latest: dict) -> bool:
    return "Bank" in (latest.get("industry") or "") or (
        _get(latest.get("current"), "SalesAndRevenue") is None
        and _get(latest.get("current"), "InterestIncome") is not None
    )


def compute(item: dict, market_cap: float | None, fx_usd: float) -> dict | None:
    """Derived metrics for one ticker (values in IDR)."""
    latest, fy = item.get("latest"), item.get("fy")
    if not latest:
        return None
    usd = "USD" in (latest.get("currency") or "")
    fx = fx_usd if usd else 1.0
    bank = is_bank(latest)
    rev_key = "InterestIncome" if bank else "SalesAndRevenue"
    inst, cur, prior = latest.get("instant", {}), latest.get("current", {}), latest.get("prior", {})

    ni_ttm = _ttm(latest, fy, NI)
    rev_ttm = _ttm(latest, fy, rev_key)
    ocf_ttm = _ttm(latest, fy, OCF)
    equity = _get(inst, "EquityAttributableToEquityOwnersOfParentEntity") or _get(inst, "Equity")
    liab = _get(inst, "Liabilities")

    ni_idr = ni_ttm * fx if ni_ttm is not None else None
    eq_idr = equity * fx if equity is not None else None
    flags = []
    if equity is not None and equity <= 0:
        flags.append("Ekuitas negatif")
    if ni_ttm is not None and ni_ttm < 0:
        flags.append("Rugi (TTM)")
    g = _growth(_get(cur, NI), _get(prior, NI))
    prior_ni, cur_ni = _get(prior, NI), _get(cur, NI)
    if prior_ni is not None and cur_ni is not None and prior_ni < 0 < cur_ni:
        flags.append("Berbalik laba YTD")
    elif prior_ni is not None and cur_ni is not None and prior_ni > 0 > cur_ni:
        flags.append("Berbalik rugi YTD")
    elif g is not None and g < -20:
        flags.append(f"Laba YTD turun {abs(g):.0f}% YoY")
    if g is not None and g > 300:
        flags.append("Laba naik dari basis kecil")
    if not bank and ocf_ttm is not None and ni_ttm and ni_ttm > 0:
        if ocf_ttm < 0:
            flags.append("Arus kas operasi negatif")
        elif ocf_ttm / ni_ttm < 0.3:
            flags.append("Laba belum jadi kas (OCF/laba < 0,3), cek laba non-operasional")
    if latest.get("opinion") and "wajar tanpa" not in latest["opinion"].lower():
        flags.append(f"Opini: {latest['opinion']}")

    return {
        "report": f"{latest.get('period')} {latest.get('year')}",
        "period_end": latest.get("end"),
        "report_type": (latest.get("type") or "").split(" / ")[0],
        "currency": "USD" if usd else "IDR",
        "bank": bank,
        "ni_ttm_bn": ni_idr / 1e9 if ni_idr is not None else None,
        "rev_ttm_bn": rev_ttm * fx / 1e9 if rev_ttm is not None else None,
        "pe": market_cap / ni_idr if market_cap and ni_idr and ni_idr > 0 else None,
        "pbv": market_cap / eq_idr if market_cap and eq_idr and eq_idr > 0 else None,
        "roe": ni_ttm / equity * 100 if ni_ttm is not None and equity and equity > 0 else None,
        "ni_growth": g,
        "rev_growth": _growth(_get(cur, rev_key), _get(prior, rev_key)),
        "net_margin": ni_ttm / rev_ttm * 100 if ni_ttm is not None and rev_ttm else None,
        "der": None if bank or not liab or not equity or equity <= 0 else liab / equity,
        "ocf_ni": None if bank or not (ocf_ttm and ni_ttm and ni_ttm > 0) else ocf_ttm / ni_ttm,
        "flags": flags,
    }


def fundamentals_table(market_caps: pd.Series, raw: dict | None = None) -> pd.DataFrame:
    raw = raw if raw is not None else load_raw()
    if not raw:
        return pd.DataFrame()
    fx = usd_idr()
    rows = {}
    for code, item in raw.get("fundamentals", {}).items():
        if item.get("error"):
            continue
        m = compute(item, market_caps.get(code), fx)
        if m:
            rows[code] = m
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.attrs.update({"usd_idr": fx, "generated": raw.get("generated")})
    return df


def recent_events(raw: dict | None = None, days: int = 30, today: date | None = None) -> list[dict]:
    """Important disclosures in the last ``days`` for all tickers, newest first."""
    raw = raw if raw is not None else load_raw()
    if not raw:
        return []
    today = today or date.today()
    out = []
    for code, events in raw.get("announcements", {}).items():
        for e in events:
            d = datetime.strptime(e["date"], "%Y-%m-%d").date()
            if (today - d).days <= days:
                out.append(
                    {**e, "code": code, "label": EVENT_LABELS.get(e["category"], e["category"])}
                )
    return sorted(out, key=lambda e: e["date"], reverse=True)
