"""One-shot ingest of the browser bundle written by scripts/idx_browser_extract.js.

`await pulseIdx.run()` on an idx.co.id tab saves one pulse_idx_YYYYMMDD.json with
fundamentals, announcements and a "market" block:

    market.summaries  {YYYYMMDD: [GetStockSummary rows]}   daily Ringkasan Saham
    market.ihsg       {YYYY-MM-DD: close}                   official COMPOSITE close
    market.hsc        [{description, date, url}]            official HSC page entries

ingest() moves the newest bundle from the Downloads folder to data/fundamentals/, writes the
missing daily summaries, appends IHSG closes and applies official HSC changes.
"""

import json
import re
import shutil
from pathlib import Path

import pandas as pd

from pulse.core.idx import IDX_DIR
from pulse.core.idx.benchmark import IHSG_OFFICIAL_FILE
from pulse.core.idx.fundamentals import FUND_DIR
from pulse.core.idx.hsc import HSC_FILE, load_hsc
from pulse.core.idx.summary import summary_files
from pulse.utils.logger import get_logger

log = get_logger(__name__)

DOWNLOADS = Path.home() / "Downloads"
_HSC_ENTRY = re.compile(r"^\s*(Pengenaan|Pencabutan)\b.*\(([A-Z]{4})\)", re.S)


def _collect_bundle() -> Path | None:
    """Move pulse_idx_*.json from Downloads into data/fundamentals; return the newest bundle."""
    FUND_DIR.mkdir(parents=True, exist_ok=True)
    for src in sorted(DOWNLOADS.glob("pulse_idx_2*.json")):
        shutil.move(str(src), FUND_DIR / src.name)
    files = sorted(FUND_DIR.glob("pulse_idx_2*.json"))
    return files[-1] if files else None


def write_summaries(summaries: dict) -> list[str]:
    """Save each day that has no file yet as data/idx/Ringkasan Saham-YYYYMMDD.json."""
    have = {re.search(r"(\d{8})", p.stem).group(1) for p in summary_files()}
    added = []
    for day, rows in sorted(summaries.items()):
        if day in have or not rows:
            continue
        path = IDX_DIR / f"Ringkasan Saham-{day}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        added.append(day)
    return added


def append_ihsg(closes: dict) -> list[str]:
    """Append official IHSG closes that are not in ihsg_official.csv yet."""
    old = (
        pd.read_csv(IHSG_OFFICIAL_FILE, dtype={"date": str})
        if IHSG_OFFICIAL_FILE.exists()
        else pd.DataFrame(columns=["date", "close"])
    )
    new = {d: c for d, c in closes.items() if d not in set(old.date) and c}
    if new:
        add = pd.DataFrame({"date": list(new), "close": list(new.values())})
        out = pd.concat([old, add], ignore_index=True).sort_values("date")
        out.to_csv(IHSG_OFFICIAL_FILE, index=False, lineterminator="\n")
    return sorted(new)


def apply_hsc(entries: list[dict]) -> dict:
    """Apply official HSC page entries to data/hsc.json.

    Returns {"added": [...], "removed": [...], "unparsed": [...]}; entries without a ticker
    (e.g. one announcement covering many stocks) are returned as unparsed for manual reading.
    """
    with open(HSC_FILE, encoding="utf-8") as f:
        data = json.load(f)
    known = {(e["code"], e["action"], e["date"]) for e in data["events"]}
    tickers = set(data["tickers"])
    added, removed, unparsed, fresh = [], [], [], []
    for e in sorted(entries, key=lambda x: x.get("date") or ""):
        day = (e.get("date") or "")[:10]
        m = _HSC_ENTRY.match(e.get("description") or "")
        if not m:
            if day > data["as_of"]:
                unparsed.append({"date": day, "description": (e.get("description") or "").strip()})
            continue
        action, code = m.group(1).lower(), m.group(2)
        if (code, action, day) in known or day <= data["as_of"]:
            continue
        fresh.append({"code": code, "action": action, "date": day})
        if action == "pengenaan":
            tickers.add(code)
            added.append(code)
        else:
            tickers.discard(code)
            removed.append(code)
    if fresh:
        data["tickers"] = sorted(tickers)
        data["events"] = fresh[::-1] + data["events"]
        data["as_of"] = max(e["date"] for e in fresh)
        with open(HSC_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        load_hsc.cache_clear()
    return {"added": added, "removed": removed, "unparsed": unparsed}


def ingest() -> str:
    """Process the newest browser bundle; returns a short report (empty if nothing to do)."""
    path = _collect_bundle()
    if path is None:
        return ""
    with open(path, encoding="utf-8") as f:
        bundle = json.load(f)
    market = bundle.pop("market", None)
    if not market:
        return ""
    days = write_summaries(market.get("summaries") or {})
    ihsg = append_ihsg(market.get("ihsg") or {})
    hsc = apply_hsc(market.get("hsc") or [])
    # simpan bundel tanpa blok market agar tetap ringan saat dimuat dashboard
    path.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")

    lines = [f"Bundel IDX {path.name}:"]
    lines.append(f"  Ringkasan Saham baru: {', '.join(days) or '-'}")
    lines.append(f"  IHSG resmi baru: {', '.join(ihsg) or '-'}")
    if hsc["added"] or hsc["removed"]:
        lines.append(f"  HSC resmi: +{hsc['added']} -{hsc['removed']}")
    for u in hsc["unparsed"]:
        lines.append(f"  HSC PERLU DIBACA MANUAL ({u['date']}): {u['description'][:120]}")
    return "\n".join(lines)
