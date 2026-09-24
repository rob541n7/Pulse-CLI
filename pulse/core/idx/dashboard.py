"""Static HTML dashboard for the big-cap swing workflow.

    python -m pulse.core.idx dashboard --open

Writes data/reports/dashboard.html: one self-contained file (data embedded as JSON,
no external scripts), so it opens offline by double-click.
"""

import json
import math
import os
import webbrowser
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from pulse.core.idx import DATA_DIR, factors, swing
from pulse.core.idx.benchmark import performance_table
from pulse.core.idx.hsc import load_hsc
from pulse.core.idx.ownership import load_ownership
from pulse.core.idx.summary import HISTORY_FILE, latest_summary, update_history
from pulse.core.idx.universe import load_universe
from pulse.utils.logger import get_logger

log = get_logger(__name__)

DASHBOARD_FILE = DATA_DIR / "reports" / "dashboard.html"
TEMPLATE_FILE = Path(__file__).with_name("dashboard_template.html")
SPARK_DAYS = 120


def _num(v, nd: int = 2):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return None if math.isnan(f) or math.isinf(f) else round(f, nd)


def _series(s: pd.Series, nd: int = 2) -> list:
    return [_num(v, nd) for v in s.tolist()]


def build_payload(params: swing.SwingParams | None = None) -> dict:
    params = params or swing.SwingParams()
    ind, bench, mcap = swing.load_market(params)
    uni = load_universe()
    tickers = [t for t in uni["tickers"] if t in ind["close"].columns]
    snap = swing.screen(ind, tickers, params)

    summary = latest_summary()
    names = summary.set_index("code")["name"]
    own = load_ownership().set_index("code")
    history = pd.read_csv(HISTORY_FILE, parse_dates=["date"]) if HISTORY_FILE.exists() else None
    ff = factors.foreign_factors(history, tickers)

    c, h, lo, v = (ind[k][tickers] for k in ("close", "high", "low", "volume"))
    cmf = factors.cmf(h, lo, c, v).iloc[-1]
    vwap = factors.vwap_premium(h, lo, c, v).iloc[-1]
    chg1d = (c.iloc[-1] / c.iloc[-2] - 1) * 100

    rows = []
    for code in snap.index:
        r = snap.loc[code]
        stage, start, age = factors.stage_with_age(ind["close"][code])
        f = ff.loc[code] if code in ff.index else pd.Series(dtype=float)
        vals = {
            "stage": stage,
            "rs13": r.rs13,
            "cmf": cmf.get(code),
            "vwap": vwap.get(code),
            "foreign": f.get("net20_pct") if f.get("days", 0) >= 5 else None,
            "big_lot": f.get("big_lot"),
        }
        labels = {k: factors.label(k, val) for k, val in vals.items()}
        closes = ind["close"][code].tail(SPARK_DAYS)
        rows.append(
            {
                "code": code,
                "name": names.get(code, ""),
                "sector": own["sector"].get(code) if "sector" in own else None,
                "close": _num(r.close, 0),
                "chg1d": _num(chg1d.get(code)),
                "mcap_t": _num(mcap[code].iloc[-1] / 1e12, 1),
                "setup": r.setup,
                "score": _num(r.score, 0),
                "rs4": _num(r.rs4, 1),
                "rs13": _num(r.rs13, 1),
                "rsi": _num(r.rsi, 0),
                "vol_ratio": _num(r.vol_ratio),
                "to_hh55": _num(r.to_hh55, 1),
                "atr_pct": _num(r.atr / r.close * 100, 1),
                "stop": _num(r.stop, 0),
                "tp1": _num(r.tp1, 0),
                "tp2": _num(r.tp2, 0),
                "risk_pct": _num(r.risk_pct, 1),
                "stage": stage,
                "stage_days": age,
                "stage_start": str(start.date()) if start is not None else None,
                "cmf": _num(vals["cmf"], 3),
                "vwap": _num(vals["vwap"], 1),
                "foreign_pct": _num(f.get("net20_pct"), 1),
                "foreign_days": int(f.get("days", 0) or 0),
                "foreign_today_bn": _num(f.get("net_today_bn"), 1),
                "foreign_net5_bn": _num(f.get("net5_bn"), 1),
                "big_lot": _num(vals["big_lot"]),
                "nonreg_pct": _num(f.get("nonreg_pct"), 1),
                "labels": labels,
                "bull": sum(v == "bull" for v in labels.values()),
                "bear": sum(v == "bear" for v in labels.values()),
                "spark": {
                    "dates": [d.strftime("%Y-%m-%d") for d in closes.index],
                    "close": _series(closes, 0),
                    "ma50": _series(ind["ma50"][code].tail(SPARK_DAYS), 0),
                    "hh55": _num(r.hh55, 0),
                },
            }
        )

    # Foreign flow hari ini (file IDX terbaru, universe saja)
    today = summary[summary.code.isin(tickers)].copy()
    today["net_bn"] = today.foreign_net * today.close / 1e9
    today = today.sort_values("net_bn")
    fmt = lambda df: [  # noqa: E731
        {"code": x.code, "net_bn": _num(x.net_bn, 1), "value_bn": _num(x.value / 1e9, 1)}
        for x in df.itertuples()
    ]

    res = swing.backtest(ind, mcap, bench, params)
    stats = {k: _num(val, 4) for k, val in res.stats().items()}
    eq = res.equity.iloc[::5]
    b = res.benchmark.reindex(eq.index).ffill()

    bb = bench.tail(250)
    perf = performance_table(bench)
    hsc_as_of, hsc = load_hsc()
    sectors = pd.Series({t: own["sector"].get(t) for t in tickers}) if "sector" in own else None

    return {
        "meta": {
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "price_date": str(ind["close"].index[-1].date()),
            "idx_file_date": str(summary.date.iloc[0].date()),
            "idx_days": int(history.date.nunique()) if history is not None else 0,
            "hsc_as_of": hsc_as_of,
            "hsc_count": len(hsc),
            "hsc_weight": _num(bench.w_hsc.iloc[-1], 4),
            "ksei_snapshot": uni.get("ksei_snapshot"),
            "universe_as_of": uni["as_of"],
            "universe_rules": uni["rules"],
            "market_ok": bool(ind["market_ok"].iloc[-1]),
            "exhsc": _num(bench.IHSG_exHSC.iloc[-1]),
            "exhsc_ma50": _num(bench.IHSG_exHSC.rolling(50).mean().iloc[-1]),
        },
        "bench": {
            "dates": [d.strftime("%Y-%m-%d") for d in bb.index],
            "ihsg": _series(bb.IHSG / bb.IHSG.iloc[0] * 100),
            "exhsc": _series(bb.IHSG_exHSC / bb.IHSG_exHSC.iloc[0] * 100),
            "perf": {
                col: {"ihsg": _num(perf.at["IHSG", col]), "exhsc": _num(perf.at["IHSG_exHSC", col])}
                for col in perf.columns
            },
        },
        "rows": rows,
        "sectors": factors.sector_rotation(ind["close"][tickers], sectors, bench.IHSG_exHSC)
        if sectors is not None
        else [],
        "foreign_today": {"buy": fmt(today.tail(8)[::-1]), "sell": fmt(today.head(8))},
        "backtest": {
            "stats": stats,
            "dates": [d.strftime("%Y-%m-%d") for d in eq.index],
            "equity": _series(eq / eq.iloc[0] * 100),
            "exhsc": _series(b.IHSG_exHSC / b.IHSG_exHSC.iloc[0] * 100),
            "ihsg": _series(b.IHSG / b.IHSG.iloc[0] * 100),
            "recent": [
                {k: (str(val) if k.endswith("date") else _num(val, 4)) for k, val in t.items()}
                for t in res.trades.tail(12).iloc[::-1].to_dict("records")
            ],
        },
    }


def _json_default(o):
    if isinstance(o, np.integer | np.floating):
        return _num(o, 4)
    return str(o)


def render(payload: dict) -> str:
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False, default=_json_default).replace("</", "<\\/")
    return template.replace("/*__PULSE_DATA__*/null", data)


def build_dashboard(open_browser: bool = False, update: bool = True) -> Path:
    """Merge new IDX Excel files, rebuild the dashboard HTML, optionally open it."""
    if update:
        update_history()
    html = render(build_payload())
    DASHBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_FILE.write_text(html, encoding="utf-8")
    log.info(f"Dashboard: {DASHBOARD_FILE}")
    if open_browser:
        if hasattr(os, "startfile"):
            os.startfile(DASHBOARD_FILE)  # type: ignore[attr-defined]
        else:
            webbrowser.open(DASHBOARD_FILE.as_uri())
    return DASHBOARD_FILE
