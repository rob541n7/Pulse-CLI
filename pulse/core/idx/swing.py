"""Swing trading (2-8 weeks) on the big-cap universe, benchmarked to IHSG ex-HSC.

Strategy "Relative-Strength Breakout" (weekly signal, next-day open execution):
    entry  : close > MA50 > MA100, 13-week return beats IHSG ex-HSC,
             close within 5% of the 55-day high, 5d volume >= 50d volume,
             stock in the top-N market cap universe on that date,
             optional market filter IHSG ex-HSC > MA50
    exit   : close < max(entry - 2 ATR, peak close - 2.5 ATR), or 40 trading days
    sizing : equal weight, max 5 positions; fees 0.15% buy / 0.25% sell
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from pulse.core.idx.benchmark import build_ihsg_ex_hsc
from pulse.core.idx.hsc import load_hsc
from pulse.core.idx.ownership import load_ownership
from pulse.core.idx.prices import fetch_panel
from pulse.core.idx.summary import latest_summary
from pulse.core.idx.universe import DELISTING_STATUS, load_universe
from pulse.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class SwingParams:
    slots: int = 5
    max_hold: int = 40  # hari bursa (~8 minggu)
    atr_stop: float = 2.0
    atr_trail: float = 2.5
    near_high_pct: float = 5.0
    buy_fee: float = 0.0015
    sell_fee: float = 0.0025
    universe_size: int = 70
    min_ff_ksei: float = 12.5
    min_avg_value: float = 5e9
    market_filter: bool = True


# ---------------------------------------------------------------- utilities


def tick_size(price: float) -> int:
    """IDX price fraction."""
    if price < 200:
        return 1
    if price < 500:
        return 2
    if price < 2000:
        return 5
    if price < 5000:
        return 10
    return 25


def round_down_tick(price: float) -> float:
    t = tick_size(price)
    return float(np.floor(price / t) * t)


def round_up_tick(price: float) -> float:
    t = tick_size(price)
    return float(np.ceil(price / t) * t)


def indicators(panel: dict[str, pd.DataFrame], index_close: pd.Series) -> dict[str, pd.DataFrame]:
    """Vectorized indicators for every ticker in the panel."""
    c = panel["close"].ffill(limit=5)
    high, low, v = panel["high"], panel["low"], panel["volume"]
    ix = index_close.reindex(c.index).ffill()

    prev = c.shift()
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()]).groupby(level=0).max()
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14).mean()
    ix13, ix4 = ix.pct_change(63), ix.pct_change(20)
    return {
        "close": c,
        "open": panel["open"],
        "ma20": c.rolling(20).mean(),
        "ma50": c.rolling(50).mean(),
        "ma100": c.rolling(100).mean(),
        "atr": tr.reindex(c.index).rolling(14, min_periods=10).mean(),
        "hh55": high.rolling(55, min_periods=40).max(),
        "vol_ratio": v.rolling(5, min_periods=3).mean() / v.rolling(50, min_periods=35).mean(),
        "value20": (c * v).rolling(20, min_periods=15).mean(),
        "rs13": c.pct_change(63).sub(ix13, axis=0),
        "rs4": c.pct_change(20).sub(ix4, axis=0),
        "rsi": 100 - 100 / (1 + up / dn),
        "market_ok": ix > ix.rolling(50).mean(),
    }


def breakout_signal(ind: dict, near_high_pct: float) -> pd.DataFrame:
    return (
        (ind["close"] > ind["ma50"])
        & (ind["ma50"] > ind["ma100"])
        & (ind["rs13"] > 0)
        & (ind["close"] >= (1 - near_high_pct / 100) * ind["hh55"])
        & (ind["vol_ratio"] >= 1.0)
    )


# ---------------------------------------------------------------- data loading


def _eligible_codes(p: SwingParams) -> list[str]:
    own = load_ownership()
    _, hsc = load_hsc()
    ok = own[
        (own.ff_ksei >= p.min_ff_ksei) & ~own.code.isin(hsc) & ~own.ff_status.isin(DELISTING_STATUS)
    ]
    return ok.code.tolist()


def load_market(p: SwingParams, refresh: bool = False):
    """Return (indicators, benchmark DataFrame, market cap DataFrame) for eligible stocks."""
    bench = build_ihsg_ex_hsc(refresh=refresh)
    summary = latest_summary()
    shares = summary.set_index("code")["listed_shares"]
    codes = [c for c in _eligible_codes(p) if c in shares.index]
    panel = fetch_panel(shares.index.tolist() + ["^JKSE"], name="all_stocks")
    panel = {f: df.reindex(columns=codes) for f, df in panel.items()}
    ind = indicators(panel, bench["IHSG_exHSC"])
    mcap = ind["close"] * shares.reindex(codes).values
    return ind, bench, mcap


# ---------------------------------------------------------------- backtest


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: pd.DataFrame
    benchmark: pd.DataFrame
    params: SwingParams

    def stats(self) -> dict:
        eq = self.equity
        years = (eq.index[-1] - eq.index[0]).days / 365.25
        t = self.trades
        return {
            "total": eq.iloc[-1] / eq.iloc[0] - 1,
            "cagr": (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1,
            "max_dd": (eq / eq.cummax() - 1).min(),
            "trades": len(t),
            "win_rate": (t.ret > 0).mean() if len(t) else 0.0,
            "avg_win": t.ret[t.ret > 0].mean() if len(t) else 0.0,
            "avg_loss": t.ret[t.ret <= 0].mean() if len(t) else 0.0,
            "avg_hold": t.days.mean() if len(t) else 0.0,
        }


def backtest(
    ind: dict, mcap: pd.DataFrame, bench: pd.DataFrame, p: SwingParams, start: str = "2023-07-01"
) -> BacktestResult:
    """Weekly-signal backtest with a point-in-time top-N market-cap universe."""
    close, opn, atr = ind["close"], ind["open"], ind["atr"]
    in_uni = (
        mcap.where(ind["value20"] >= p.min_avg_value).rank(axis=1, ascending=False)
        <= p.universe_size
    )
    signal = breakout_signal(ind, p.near_high_pct) & in_uni
    dates = close.loc[start:].index
    week_end = set(pd.Series(dates, index=dates).groupby(dates.to_period("W")).max())

    cash, pos, trades, equity = 1.0, {}, [], []
    to_buy: list[str] = []
    to_sell: list[str] = []
    for d in dates:
        for code in to_sell:
            ps = pos.pop(code)
            px = opn.at[d, code] if not np.isnan(opn.at[d, code]) else close.at[d, code]
            cash += ps["shares"] * px * (1 - p.sell_fee)
            trades.append(
                {
                    "code": code,
                    "entry_date": ps["date"].date(),
                    "exit_date": d.date(),
                    "entry": ps["entry"],
                    "exit": px,
                    "days": ps["age"],
                    "reason": ps["reason"],
                    "ret": px * (1 - p.sell_fee) / (ps["entry"] * (1 + p.buy_fee)) - 1,
                }
            )
        to_sell = []

        nav = cash + sum(ps["shares"] * close.at[d, c] for c, ps in pos.items())
        for code in to_buy:
            px = opn.at[d, code]
            if np.isnan(px) or px <= 0 or len(pos) >= p.slots:
                continue
            alloc = min(nav / p.slots, cash)
            shares = alloc / (px * (1 + p.buy_fee))
            cash -= shares * px * (1 + p.buy_fee)
            a = atr.at[d, code]
            pos[code] = {
                "shares": shares,
                "entry": px,
                "date": d,
                "age": 0,
                "atr": a,
                "stop": px - p.atr_stop * a,
                "peak": px,
                "reason": "",
            }
        to_buy = []

        for code, ps in pos.items():
            c = close.at[d, code]
            ps["age"] += 1
            ps["peak"] = max(ps["peak"], c)
            if c < max(ps["stop"], ps["peak"] - p.atr_trail * ps["atr"]):
                ps["reason"] = "trailing" if ps["peak"] > ps["entry"] else "stop"
                to_sell.append(code)
            elif ps["age"] >= p.max_hold:
                ps["reason"] = "waktu"
                to_sell.append(code)
        equity.append(cash + sum(ps["shares"] * close.at[d, c] for c, ps in pos.items()))

        if d in week_end and (not p.market_filter or ind["market_ok"].at[d]):
            free = p.slots - len(pos) + len(to_sell)
            if free > 0:
                cand = ind["rs13"].loc[d][signal.loc[d]].drop(labels=list(pos), errors="ignore")
                to_buy = cand.sort_values(ascending=False).index[:free].tolist()

    return BacktestResult(
        pd.Series(equity, index=dates), pd.DataFrame(trades), bench.loc[start:], p
    )


# ---------------------------------------------------------------- screener


def classify(r: pd.Series, near_high_pct: float = 5.0) -> str:
    uptrend = r.close > r.ma50 > r.ma100
    if uptrend and r.rs13 > 0 and r.to_hh55 >= -near_high_pct and r.vol_ratio >= 1.0:
        return "BREAKOUT"
    if uptrend and r.rs13 > 0 and r.close <= r.ma20 + 0.5 * r.atr and 38 <= r.rsi <= 55:
        return "PULLBACK"
    if r.close > r.ma20 > r.ma50 and r.rs13 > 0:
        return "TREND"
    if r.close < r.ma50 and r.rs13 < 0:
        return "HINDARI"
    return "NETRAL"


def screen(ind: dict, tickers: list[str], p: SwingParams) -> pd.DataFrame:
    """Latest setup, score and trade levels for each ticker."""
    d = ind["close"].index[-1]
    tickers = [t for t in tickers if t in ind["close"].columns]
    snap = pd.DataFrame(
        {
            k: ind[k].loc[d, tickers]
            for k in ("close", "ma20", "ma50", "ma100", "atr", "hh55", "vol_ratio", "rsi")
        }
    )
    snap["rs13"] = ind["rs13"].loc[d, tickers] * 100
    snap["rs4"] = ind["rs4"].loc[d, tickers] * 100
    snap["to_hh55"] = (snap.close / snap.hh55 - 1) * 100
    snap["setup"] = snap.apply(classify, axis=1, near_high_pct=p.near_high_pct)
    snap["score"] = (
        snap.rs13.rank(pct=True) * 0.5
        + snap.rs4.rank(pct=True) * 0.3
        + snap.to_hh55.rank(pct=True) * 0.2
    ) * 100
    snap["stop"] = [round_down_tick(c - p.atr_stop * a) for c, a in zip(snap.close, snap.atr)]
    risk = snap.close - snap.stop
    snap["tp1"] = [round_up_tick(c + 2 * r) for c, r in zip(snap.close, risk)]
    snap["tp2"] = [round_up_tick(c + 3 * r) for c, r in zip(snap.close, risk)]
    snap["risk_pct"] = risk / snap.close * 100
    snap.attrs["date"] = d
    snap.attrs["market_ok"] = bool(ind["market_ok"].iloc[-1])
    return snap.sort_values("score", ascending=False)


# ---------------------------------------------------------------- formatting

SETUP_NOTES = {
    "BREAKOUT": "setup yang di-backtest",
    "PULLBACK": "watchlist, belum di-backtest",
    "TREND": "sedang naik, tunggu breakout berikutnya",
}


def _row(code: str, r: pd.Series) -> str:
    return (
        f"  {code:<5} {r.close:>8,.0f}  RS13 {r.rs13:>+6.1f}%  RS4 {r.rs4:>+6.1f}%  "
        f"RSI {r.rsi:>4.0f}  SL {r.stop:>7,.0f} ({-r.risk_pct:.1f}%)  "
        f"TP {r.tp1:,.0f}/{r.tp2:,.0f}"
    )


def format_screen(snap: pd.DataFrame) -> str:
    d, ok = snap.attrs["date"], snap.attrs["market_ok"]
    lines = [
        f"SWING SCREENER 2-8 minggu - {len(snap)} big cap, data {d.date()}",
        f"Pasar: IHSG ex-HSC {'DI ATAS' if ok else 'DI BAWAH'} MA50 -> "
        f"{'entry diizinkan' if ok else 'tahan entry baru'}",
        "RS = selisih return vs IHSG ex-HSC. SL = entry - 2 ATR, TP = 2R / 3R.",
        "Counts: " + ", ".join(f"{k} {v}" for k, v in snap.setup.value_counts().items()),
    ]
    for setup, note in SETUP_NOTES.items():
        sub = snap[snap.setup == setup]
        if len(sub):
            lines.append(f"\n{setup} ({note})")
            lines += [_row(code, r) for code, r in sub.iterrows()]
    weak = snap[snap.setup == "HINDARI"].tail(8)
    if len(weak):
        lines.append("\nHINDARI (terlemah): " + ", ".join(weak.index[::-1]))
    lines.append("\nBukan rekomendasi beli/jual. Lakukan riset sendiri (DYOR).")
    return "\n".join(lines)


def format_ticker(code: str, snap: pd.DataFrame) -> str:
    if code not in snap.index:
        return f"{code} tidak ada di universe big cap. Cek /universe."
    r = snap.loc[code]
    rank = list(snap.index).index(code) + 1
    return "\n".join(
        [
            f"SWING: {code} - setup {r.setup} (peringkat {rank}/{len(snap)}, skor {r.score:.0f})",
            f"Harga {r.close:,.0f} | MA20 {r.ma20:,.0f} | MA50 {r.ma50:,.0f} | MA100 {r.ma100:,.0f}",
            f"Relatif vs IHSG ex-HSC: 4 minggu {r.rs4:+.1f}%, 13 minggu {r.rs13:+.1f}%",
            f"Jarak ke high 55 hari {r.to_hh55:+.1f}% | Volume 5d/50d {r.vol_ratio:.2f}x | RSI {r.rsi:.0f}",
            f"ATR14 {r.atr:,.0f} ({r.atr / r.close * 100:.1f}%)",
            "",
            f"Level (jika entry di {r.close:,.0f}):",
            f"  Stop loss : {r.stop:,.0f} ({-r.risk_pct:.1f}%)",
            f"  TP1 (2R)  : {r.tp1:,.0f}",
            f"  TP2 (3R)  : {r.tp2:,.0f}",
            "  Trailing  : puncak close - 2.5 ATR, maksimal 8 minggu",
        ]
    )


def format_backtest(res: BacktestResult) -> str:
    s = res.stats()
    b = res.benchmark
    lines = [
        f"BACKTEST Relative-Strength Breakout {res.equity.index[0].date()} - {res.equity.index[-1].date()}",
        f"Universe dinamis top {res.params.universe_size} market cap, max {res.params.slots} posisi, "
        f"filter pasar {'ON' if res.params.market_filter else 'OFF'}",
        "",
        f"{'':<14} {'Total':>9} {'CAGR':>8} {'MaxDD':>8}",
        f"{'Strategi':<14} {s['total']:>+8.1%} {s['cagr']:>+7.1%} {s['max_dd']:>+7.1%}",
    ]
    for col, label in (("IHSG", "IHSG"), ("IHSG_exHSC", "IHSG ex-HSC")):
        x = b[col].dropna()
        yrs = (x.index[-1] - x.index[0]).days / 365.25
        dd = (x / x.cummax() - 1).min()
        tot = x.iloc[-1] / x.iloc[0] - 1
        lines.append(f"{label:<14} {tot:>+8.1%} {(1 + tot) ** (1 / yrs) - 1:>+7.1%} {dd:>+7.1%}")
    lines += [
        "",
        f"Trade {s['trades']} | win rate {s['win_rate']:.0%} | rata-rata menang {s['avg_win']:+.1%} "
        f"/ kalah {s['avg_loss']:+.1%} | hold {s['avg_hold']:.0f} hari",
        "Catatan: free float & HSC memakai data terkini untuk seluruh periode, jumlah saham",
        "dianggap tetap -> hasil cenderung optimistis.",
    ]
    return "\n".join(lines)


def current_universe() -> list[str]:
    return load_universe()["tickers"]
