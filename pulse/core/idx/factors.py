"""Per-stock factors, shown side by side (not blended into one score).

Chosen for low noise on liquid big caps, using only data Pulse already has:

    Fase        Stage analysis on the 150-day (30-week) MA, debounced 5 days
    RS 13w      Return vs IHSG ex-HSC over 13 weeks
    CMF 20      Chaikin Money Flow: closing position within the day's range x volume
    VWAP 20     Close vs 20-day VWAP (premium / discount to where volume traded)
    Asing 20d   Net foreign buy as % of traded value (IDX Excel history)
    Lot besar   Average value per trade today vs 20-day average (IDX Excel history)
"""

import numpy as np
import pandas as pd

STAGE_MA = 150
STAGE_SLOPE_DAYS = 20
STAGE_FLAT = 0.01  # |slope MA150 20 hari| < 1% dianggap datar
DEBOUNCE = 5  # fase baru harus bertahan 5 hari

MARKUP, MARKDOWN, AKUMULASI, DISTRIBUSI = "MARKUP", "MARKDOWN", "AKUMULASI", "DISTRIBUSI"


def raw_stage(close: pd.DataFrame) -> pd.DataFrame:
    ma = close.rolling(STAGE_MA, min_periods=int(STAGE_MA * 0.8)).mean()
    slope = ma / ma.shift(STAGE_SLOPE_DAYS) - 1
    # Zona netral: setelah MA150 turun = akumulasi, setelah MA150 naik = distribusi
    prior = ma / ma.shift(60) - 1
    out = pd.DataFrame(
        np.where(prior < 0, AKUMULASI, DISTRIBUSI), index=close.index, columns=close.columns
    )
    out = out.mask((close > ma) & (slope > STAGE_FLAT), MARKUP)
    out = out.mask((close < ma) & (slope < -STAGE_FLAT), MARKDOWN)
    return out.where(ma.notna())


def debounce(stage: pd.Series, n: int = DEBOUNCE) -> pd.Series:
    """Only switch to a new stage after it holds for n consecutive days."""
    vals = stage.to_numpy(dtype=object)
    out = np.empty(len(vals), dtype=object)
    current, candidate, count = None, None, 0
    for i, v in enumerate(vals):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            out[i] = current
            continue
        if current is None:
            current = v
        elif v != current:
            if v == candidate:
                count += 1
            else:
                candidate, count = v, 1
            if count >= n:
                current, candidate, count = v, None, 0
        else:
            candidate, count = None, 0
        out[i] = current
    return pd.Series(out, index=stage.index)


def stage_with_age(close: pd.Series) -> tuple[str | None, pd.Timestamp | None, int]:
    """(current stage, start date, trading days in stage) for one ticker."""
    s = debounce(raw_stage(close.to_frame())[close.name]).dropna()
    if s.empty:
        return None, None, 0
    current = s.iloc[-1]
    changed = s[s != current]
    start = s.index[0] if changed.empty else s.loc[changed.index[-1] :].index[1]
    return current, start, int((s.index >= start).sum())


def cmf(high, low, close, volume, n: int = 20):
    rng = (high - low).replace(0, np.nan)
    mfm = (((close - low) - (high - close)) / rng).fillna(0)
    return (mfm * volume).rolling(n, min_periods=int(n * 0.75)).sum() / volume.rolling(
        n, min_periods=int(n * 0.75)
    ).sum()


def vwap_premium(high, low, close, volume, n: int = 20):
    typical = (high + low + close) / 3
    vwap = (typical * volume).rolling(n, min_periods=int(n * 0.75)).sum() / volume.rolling(
        n, min_periods=int(n * 0.75)
    ).sum()
    return (close / vwap - 1) * 100


def foreign_factors(history: pd.DataFrame, codes: list[str]) -> pd.DataFrame:
    """Foreign net flow & trade-size factors from accumulated IDX Excel history."""
    cols = ["days", "net5_bn", "net20_bn", "net20_pct", "net_today_bn", "big_lot", "nonreg_pct"]
    if history is None or history.empty:
        return pd.DataFrame(index=codes, columns=cols, dtype=float)

    h = history[history.code.isin(codes)]
    piv = {
        k: h.pivot_table(index="date", columns="code", values=k, aggfunc="last")
        .reindex(columns=codes)
        .sort_index()
        for k in ("foreign_net", "close", "value", "frequency", "nonreg_value")
    }
    # Foreign Buy/Sell di file IDX dalam lembar -> rupiah (aproksimasi harga penutupan)
    net = piv["foreign_net"] * piv["close"]
    value = piv["value"]
    size = value / piv["frequency"].replace(0, np.nan)
    out = pd.DataFrame(index=codes)
    out["days"] = net.notna().sum()
    out["net5_bn"] = net.tail(5).sum(min_count=1) / 1e9
    out["net20_bn"] = net.tail(20).sum(min_count=1) / 1e9
    out["net20_pct"] = net.tail(20).sum(min_count=1) / value.tail(20).sum(min_count=1) * 100
    out["net_today_bn"] = net.iloc[-1] / 1e9
    prev = size.iloc[:-1].tail(19)
    out["big_lot"] = (size.iloc[-1] / prev.mean()).where(prev.notna().sum() >= 5)
    out["nonreg_pct"] = piv["nonreg_value"].iloc[-1] / value.iloc[-1] * 100
    return out


def sector_rotation(
    close: pd.DataFrame, sectors: pd.Series, bench: pd.Series, trail: int = 5, step: int = 5
) -> list[dict]:
    """Relative Rotation Graph per sector (equal-weight members vs IHSG ex-HSC).

    RS-Ratio = 100 x (sector / benchmark) / its 63-day mean
    RS-Momentum = 100 x RS-Ratio / RS-Ratio 10 days ago
    """
    ret = close.pct_change(fill_method=None)
    b = bench.reindex(close.index).ffill()
    out = []
    for sector, members in sectors.dropna().groupby(sectors.dropna()):
        cols = [c for c in members.index if c in close.columns]
        if len(cols) < 2:
            continue
        idx = (1 + ret[cols].mean(axis=1).fillna(0)).cumprod()
        rel = idx / b
        ratio = 100 * rel / rel.rolling(63).mean()
        mom = 100 * ratio / ratio.shift(10)
        pts = pd.DataFrame({"x": ratio, "y": mom}).dropna().iloc[::-step][:trail][::-1]
        if pts.empty:
            continue
        x, y = pts.x.iloc[-1], pts.y.iloc[-1]
        quad = (
            ("LEADING" if y >= 100 else "WEAKENING")
            if x >= 100
            else ("IMPROVING" if y >= 100 else "LAGGING")
        )
        out.append(
            {
                "sector": sector,
                "n": len(cols),
                "quadrant": quad,
                "ret20": float((idx.iloc[-1] / idx.iloc[-21] - 1) * 100),
                "trail": [[round(float(a), 2), round(float(c), 2)] for a, c in zip(pts.x, pts.y)],
            }
        )
    return out


def label(factor: str, v) -> str:
    """'bull' / 'bear' / 'neutral' / 'na' for a factor value."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "na"
    rules = {
        "stage": lambda x: {MARKUP: "bull", MARKDOWN: "bear"}.get(x, "neutral"),
        "rs13": lambda x: "bull" if x > 5 else "bear" if x < -5 else "neutral",
        "cmf": lambda x: "bull" if x > 0.05 else "bear" if x < -0.05 else "neutral",
        "vwap": lambda x: "neutral",
        "foreign": lambda x: "bull" if x > 2 else "bear" if x < -2 else "neutral",
        "big_lot": lambda x: "bull" if x > 1.3 else "neutral",
    }
    return rules[factor](v)
