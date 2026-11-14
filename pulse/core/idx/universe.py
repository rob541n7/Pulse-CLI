"""Big-cap universe: large, liquid, genuinely free-floating, non-HSC stocks.

The universe is locked once a month: every build is also saved as a snapshot in
data/universe/snapshots/bigcap_YYYYMM.json together with the eligible stocks and their
listed shares on that date. The backtest reads those snapshots point-in-time (the first
one also covers all earlier history), so later ownership / HSC changes never rewrite
past results.
"""

import json
from dataclasses import asdict, dataclass
from datetime import date

import pandas as pd

from pulse.core.idx import UNIVERSE_DIR
from pulse.core.idx.hsc import load_hsc
from pulse.core.idx.ownership import load_ownership
from pulse.core.idx.prices import fetch_panel
from pulse.core.idx.summary import latest_summary
from pulse.utils.logger import get_logger

log = get_logger(__name__)

UNIVERSE_FILE = UNIVERSE_DIR / "bigcap.json"
SNAPSHOT_DIR = UNIVERSE_DIR / "snapshots"
DELISTING_STATUS = {"Voluntary Delisting", "Force Delisting"}


@dataclass
class UniverseRules:
    size: int = 70
    min_ff_ksei: float = 12.5  # % saham di luar pemegang >=1% (KSEI)
    min_avg_value_bn: float = 5.0  # rata-rata nilai transaksi 20 hari, miliar Rp
    candidates: int = 250  # kandidat teratas (market cap) yang dicek likuiditasnya


def exclusion_reason(row: pd.Series, rules: UniverseRules, hsc: frozenset[str]) -> str:
    """Why a stock is excluded ('' if it qualifies)."""
    if row.code in hsc:
        return "HSC"
    if row.get("ff_status") in DELISTING_STATUS:
        return "delisting"
    if pd.isna(row.get("ff_ksei")) or row.ff_ksei < rules.min_ff_ksei:
        return f"free float < {rules.min_ff_ksei:g}%"
    if pd.isna(row.get("avg_value_bn")) or row.avg_value_bn < rules.min_avg_value_bn:
        return f"likuiditas < Rp {rules.min_avg_value_bn:g} M"
    return ""


def build_universe(rules: UniverseRules | None = None, refresh_ownership: bool = False) -> dict:
    """Build the universe from the latest IDX summary + ownership + price liquidity."""
    rules = rules or UniverseRules()
    summary = latest_summary()
    if summary is None:
        raise FileNotFoundError("Taruh file 'Ringkasan Saham-YYYYMMDD.xlsx' di data/idx/ dulu")

    hsc_as_of, hsc = load_hsc()
    own = load_ownership(refresh=refresh_ownership)
    df = (
        summary[["code", "name", "close", "listed_shares", "market_cap"]]
        .merge(own, on="code", how="left")
        .sort_values("market_cap", ascending=False)
        .head(rules.candidates)
    )

    panel = fetch_panel(
        df.code.tolist(),
        start=str((summary.date.iloc[0] - pd.Timedelta(days=60)).date()),
        name="universe_candidates",
        refresh=True,
    )
    value = (panel["close"] * panel["volume"]).tail(20).mean() / 1e9
    df["avg_value_bn"] = df.code.map(value)
    df["excluded"] = df.apply(exclusion_reason, axis=1, rules=rules, hsc=hsc)

    members = df[df.excluded == ""].head(rules.size)
    cutoff_mcap = members.market_cap.min()
    excluded = df[(df.excluded != "") & (df.market_cap >= cutoff_mcap)]

    shares = summary.set_index("code")["listed_shares"]
    result = {
        "as_of": str(summary.date.iloc[0].date()),
        "hsc_as_of": hsc_as_of,
        "ksei_snapshot": own["ksei_snapshot"].dropna().iloc[0] if "ksei_snapshot" in own else None,
        "rules": asdict(rules),
        "tickers": members.code.tolist(),
        "members": members[
            ["code", "name", "market_cap", "avg_value_bn", "ff_bei", "ff_ksei", "sector"]
        ]
        .round(2)
        .to_dict("records"),
        "excluded": excluded[["code", "market_cap", "ff_ksei", "avg_value_bn", "excluded"]]
        .round(2)
        .to_dict("records"),
        "eligible": eligible_shares(own, hsc, shares, rules.min_ff_ksei),
        "hsc_tickers": sorted(hsc),
    }
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    with open(UNIVERSE_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    save_snapshot(result)
    log.info(f"Universe: {len(members)} saham, {len(excluded)} big cap dieliminasi")
    return result


def eligible_shares(own: pd.DataFrame, hsc, shares: pd.Series, min_ff_ksei: float) -> dict:
    """{code: listed shares} of every stock that passes free float / HSC / delisting rules."""
    ok = own[
        (own.ff_ksei >= min_ff_ksei) & ~own.code.isin(hsc) & ~own.ff_status.isin(DELISTING_STATUS)
    ]
    return {c: float(shares[c]) for c in ok.code if c in shares.index and pd.notna(shares[c])}


def save_snapshot(u: dict) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"bigcap_{u['as_of'][:7].replace('-', '')}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(u, f, ensure_ascii=False, default=str)


def snapshots() -> list[dict]:
    """Monthly locked universes, oldest first."""
    out = []
    for path in sorted(SNAPSHOT_DIR.glob("bigcap_*.json")):
        with open(path, encoding="utf-8") as f:
            out.append(json.load(f))
    return sorted(out, key=lambda u: u["as_of"])


def history_hsc() -> tuple[str, frozenset[str]] | None:
    """(as_of, HSC list) frozen in the first snapshot, used for all pre-Nov-2026 history."""
    for s in snapshots():
        if s.get("hsc_tickers"):
            return s["hsc_as_of"], frozenset(s["hsc_tickers"])
    return None


def rebuild_due(latest: date) -> bool:
    """True when the monthly lock should be renewed for the session `latest`.

    One snapshot per month, taken on the month's last weekday (or on the first run after
    a month ended without one). Within a locked month nothing changes.
    """
    snaps = snapshots()
    if not snaps:
        return True
    last = date.fromisoformat(snaps[-1]["as_of"])
    months = (latest.year - last.year) * 12 + latest.month - last.month
    if months <= 0:
        return False
    if months >= 2:
        return True
    nxt = latest + pd.Timedelta(days=3 if latest.weekday() == 4 else 1)
    return nxt.month != latest.month


def load_universe() -> dict:
    """Load the saved universe (data/universe/bigcap.json)."""
    if not UNIVERSE_FILE.exists():
        raise FileNotFoundError("Universe belum dibuat. Jalankan: /universe rebuild")
    with open(UNIVERSE_FILE, encoding="utf-8") as f:
        return json.load(f)


def format_universe(u: dict, show_excluded: bool = True) -> str:
    lines = [
        f"BIG CAP UNIVERSE ({len(u['tickers'])} saham) - data {u['as_of']}",
        f"Aturan: free float KSEI >= {u['rules']['min_ff_ksei']:g}%, "
        f"likuiditas >= Rp {u['rules']['min_avg_value_bn']:g} M/hari, bukan HSC "
        f"(daftar HSC {u['hsc_as_of']}, KSEI {u.get('ksei_snapshot')})",
        "",
    ]
    codes = u["tickers"]
    for i in range(0, len(codes), 10):
        lines.append("  " + " ".join(f"{c:<5}" for c in codes[i : i + 10]))
    smallest = min(u["members"], key=lambda m: m["market_cap"])
    lines.append(f"\nTerkecil: {smallest['code']} (Rp {smallest['market_cap'] / 1e12:,.1f} T)")
    if show_excluded and u["excluded"]:
        lines.append("\nBig cap yang dieliminasi:")
        for e in u["excluded"][:25]:
            lines.append(f"  {e['code']:<5} Rp {e['market_cap'] / 1e12:>6,.1f} T  {e['excluded']}")
        if len(u["excluded"]) > 25:
            lines.append(f"  ... +{len(u['excluded']) - 25} lainnya")
    return "\n".join(lines)
