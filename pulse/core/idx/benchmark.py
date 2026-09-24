"""IHSG ex-HSC benchmark.

HSC stocks carry a large index weight (~26% in Sep 2026) while their prices are
driven by a handful of holders, so relative strength vs plain IHSG is distorted.

Method: take the official IHSG daily return and strip out the HSC contribution

    r_ex = (r_IHSG - w_hsc * r_hsc) / (1 - w_hsc)

where w_hsc is HSC's share of total market cap (previous close x listed shares)
and r_hsc is the cap-weighted HSC return.
"""

import pandas as pd

from pulse.core.idx.hsc import load_hsc
from pulse.core.idx.prices import fetch_panel
from pulse.core.idx.summary import latest_summary
from pulse.utils.logger import get_logger

log = get_logger(__name__)

IHSG_SYMBOL = "^JKSE"
MAX_DAILY_MOVE = 0.35  # batas ARA/ARB; lebih dari ini dianggap data rusak


def ex_hsc_returns(
    ihsg_ret: pd.Series, stock_ret: pd.DataFrame, mcap_prev: pd.DataFrame, hsc: set[str]
) -> tuple[pd.Series, pd.Series]:
    """Return (ex-HSC daily return, HSC weight) given aligned inputs."""
    cols = [c for c in stock_ret.columns if c in hsc]
    total = mcap_prev.sum(axis=1)
    w_hsc = mcap_prev[cols].sum(axis=1) / total
    valid_w = mcap_prev[cols].where(stock_ret[cols].notna())
    r_hsc = (stock_ret[cols] * mcap_prev[cols]).sum(axis=1) / valid_w.sum(axis=1)
    r_ex = (ihsg_ret - w_hsc * r_hsc.fillna(0)) / (1 - w_hsc)
    return r_ex, w_hsc


def build_ihsg_ex_hsc(start: str = "2023-01-01", refresh: bool = False) -> pd.DataFrame:
    """DataFrame with columns IHSG, IHSG_exHSC, w_hsc (index = trading date)."""
    summary = latest_summary()
    if summary is None:
        raise FileNotFoundError(
            "Butuh file Ringkasan Saham di data/idx/ untuk jumlah saham tercatat"
        )
    shares = summary.set_index("code")["listed_shares"]
    _, hsc = load_hsc()

    panel = fetch_panel(
        shares.index.tolist() + [IHSG_SYMBOL], start=start, name="all_stocks", refresh=refresh
    )
    close = panel["close"]
    ihsg = close.pop(IHSG_SYMBOL).dropna()
    close = close.reindex(ihsg.index).ffill(limit=5)
    ret = close.pct_change(fill_method=None).clip(-MAX_DAILY_MOVE, MAX_DAILY_MOVE)
    mcap_prev = close.shift(1) * shares.reindex(close.columns)

    r_ex, w_hsc = ex_hsc_returns(ihsg.pct_change(), ret, mcap_prev, hsc)
    out = pd.DataFrame(
        {
            "IHSG": ihsg,
            "IHSG_exHSC": (1 + r_ex.fillna(0)).cumprod() * ihsg.iloc[0],
            "w_hsc": w_hsc,
        }
    )
    return out


def performance_table(bench: pd.DataFrame) -> pd.DataFrame:
    """Returns (%) over standard lookbacks for IHSG and IHSG ex-HSC."""
    s = bench[["IHSG", "IHSG_exHSC"]]
    last = s.iloc[-1]
    ytd_base = s[s.index.year == s.index[-1].year].iloc[0]
    periods = {"1 minggu": 5, "1 bulan": 21, "3 bulan": 63, "6 bulan": 126, "1 tahun": 250}
    cols = {k: (last / s.iloc[-1 - n] - 1) * 100 for k, n in periods.items() if len(s) > n}
    cols["YTD"] = (last / ytd_base - 1) * 100
    return pd.DataFrame(cols)


def format_benchmark(bench: pd.DataFrame) -> str:
    perf = performance_table(bench)
    hsc_as_of, hsc = load_hsc()
    lines = [
        f"IHSG vs IHSG ex-HSC (data s/d {bench.index[-1].date()})",
        f"Bobot {len(hsc)} saham HSC di IHSG: {bench.w_hsc.iloc[-1]:.1%} (daftar HSC {hsc_as_of})",
        "",
        f"{'Periode':<10} {'IHSG':>9} {'ex-HSC':>9} {'Selisih':>9}",
    ]
    for p in perf.columns:
        a, b = perf.at["IHSG", p], perf.at["IHSG_exHSC", p]
        lines.append(f"{p:<10} {a:>+8.2f}% {b:>+8.2f}% {b - a:>+8.2f}%")
    lines.append(
        f"\nIHSG ex-HSC: {bench.IHSG_exHSC.iloc[-1]:,.2f} | "
        f"MA50: {bench.IHSG_exHSC.rolling(50).mean().iloc[-1]:,.2f}"
    )
    return "\n".join(lines)
