"""IHSG ex-HSC benchmark.

HSC stocks carry a large index weight (~26% in Sep 2026) while their prices are
driven by a handful of holders, so relative strength vs plain IHSG is distorted.

Method: take the official IHSG daily return and strip out the HSC contribution

    r_ex = (r_IHSG - w_hsc * r_hsc) / (1 - w_hsc)

with weights as IDX computes IHSG: capped free-float adjusted market cap (cap 9% per
stock, previous close x listed shares x free float BEI), Papan Akselerasi excluded.
w_hsc is HSC's share of that and r_hsc the weighted HSC return.

From 2 Nov 2026 (Peng-00201/BEI.POP/10-2026) the official IHSG itself excludes HSC stocks
(and adjusts at once when a stock enters/leaves HSC), so from then on ex-HSC simply
follows the official IHSG return.
"""

import numpy as np
import pandas as pd

from pulse.core.idx import DATA_DIR
from pulse.core.idx.hsc import load_hsc
from pulse.core.idx.ownership import load_ownership
from pulse.core.idx.prices import PriceDownloadError, fetch_panel
from pulse.core.idx.summary import latest_summary
from pulse.utils.logger import get_logger

log = get_logger(__name__)

IHSG_SYMBOL = "^JKSE"
# Penutupan IHSG resmi dari idx.co.id (GetIndexSummary, COMPOSITE) untuk menambal hari yang
# kosong di Yahoo; kolom: date,close
IHSG_OFFICIAL_FILE = DATA_DIR / "idx" / "ihsg_official.csv"
MAX_DAILY_MOVE = 0.35  # batas ARA/ARB; lebih dari ini dianggap data rusak
IHSG_CAP = 0.09  # bobot maksimum per saham di IHSG
NEW_METHOD_FROM = pd.Timestamp("2026-11-02")  # IHSG resmi tanpa HSC (Peng-00201/BEI.POP/10-2026)


def cap_weights(mcap: pd.DataFrame, cap: float | None = IHSG_CAP) -> pd.DataFrame:
    """Row-wise index weights from (free float) market cap, capped and redistributed."""
    m = mcap.fillna(0).clip(lower=0)
    w = m.div(m.sum(axis=1), axis=0).fillna(0)
    if not cap:
        return w
    feasible = ((m > 0).sum(axis=1) * cap) >= 1
    arr, tol = w.to_numpy(copy=True), 1e-12
    for i in np.flatnonzero(feasible.to_numpy()):
        row = arr[i]
        while (row > cap + tol).any():
            excess = (row - cap).clip(min=0).sum()
            row = np.minimum(row, cap)
            free = np.where(row < cap - tol, row, 0)
            row = row + free / free.sum() * excess
        arr[i] = row
    return pd.DataFrame(arr, index=w.index, columns=w.columns)


def ex_hsc_returns(
    ihsg_ret: pd.Series,
    stock_ret: pd.DataFrame,
    mcap_prev: pd.DataFrame,
    hsc: set[str],
    cap: float | None = IHSG_CAP,
    official_from: pd.Timestamp | None = NEW_METHOD_FROM,
) -> tuple[pd.Series, pd.Series]:
    """Return (ex-HSC daily return, HSC weight in IHSG) given aligned inputs.

    mcap_prev: previous-day free float market cap of the IHSG constituents.
    """
    cols = [c for c in stock_ret.columns if c in hsc]
    w = cap_weights(mcap_prev, cap)
    w_hsc = w[cols].sum(axis=1)
    valid_w = w[cols].where(stock_ret[cols].notna())
    r_hsc = (stock_ret[cols] * w[cols]).sum(axis=1) / valid_w.sum(axis=1)
    r_ex = (ihsg_ret - w_hsc * r_hsc.fillna(0)) / (1 - w_hsc)
    if official_from is not None:
        r_ex = r_ex.where(r_ex.index < official_from, ihsg_ret)
    return r_ex, w_hsc


def official_ihsg() -> pd.Series:
    if not IHSG_OFFICIAL_FILE.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(IHSG_OFFICIAL_FILE, parse_dates=["date"])
    return df.set_index("date")["close"].astype(float)


def free_float() -> pd.Series:
    """Free float fraction per code (BEI, else KSEI); NaN for Papan Akselerasi (not in IHSG)."""
    own = load_ownership().set_index("code")
    ff = own["ff_bei"].fillna(own["ff_ksei"]) / 100
    return ff.where(own["board"] != "Akselerasi")


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
    ihsg = official_ihsg().combine_first(close.pop(IHSG_SYMBOL))
    ihsg = ihsg[ihsg.index <= summary.date.iloc[0]].dropna()  # tanpa sesi berjalan
    if ihsg.empty:
        raise PriceDownloadError("Data IHSG (^JKSE) kosong dari Yahoo. Coba lagi 15-60 menit lagi.")
    close = close.reindex(ihsg.index).ffill(limit=5)
    ret = close.pct_change(fill_method=None).clip(-MAX_DAILY_MOVE, MAX_DAILY_MOVE)
    known = free_float()
    ff = known.reindex(close.columns).fillna(known.median())  # emiten baru: median
    ff[ff.index.isin(known.index[known.isna()])] = 0  # Papan Akselerasi tidak masuk IHSG
    mcap_prev = close.shift(1) * shares.reindex(close.columns) * ff

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
        f"Bobot {len(hsc)} saham HSC di IHSG: {bench.w_hsc.iloc[-1]:.1%} (free float, cap 9%; "
        f"daftar HSC {hsc_as_of})",
        f"Mulai {NEW_METHOD_FROM.date()} IHSG resmi sudah tanpa HSC: ex-HSC = IHSG resmi",
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
