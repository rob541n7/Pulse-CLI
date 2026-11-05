"""Broker flow (bandar detector) for the big-cap universe via the user's own Stockbit token.

Per ticker two requests: the latest session and the last 20 sessions (one date-range call).
The token is read by StockbitClient from STOCKBIT_TOKEN / STOCKBIT_TOKEN_FILE; it is never
printed or stored here. Results go to data/brokerflow/broker_YYYYMMDD.json.
"""

import asyncio
import json
from datetime import date
from pathlib import Path

from pulse.core.idx import DATA_DIR
from pulse.core.idx.summary import history_dates
from pulse.utils.logger import get_logger

log = get_logger(__name__)

BROKER_DIR = DATA_DIR / "brokerflow"
WINDOW = 20
PAUSE_S = 0.6

# "Small Acc/Dist" sengaja netral: terlalu kecil untuk dibaca sebagai sinyal
BULL = {"big acc", "normal acc", "acc", "accumulation"}
BEAR = {"big dist", "normal dist", "dist", "distribution"}


def _accdist(raw: dict, *keys: str) -> str | None:
    node = raw
    for k in keys:
        node = (node or {}).get(k) if isinstance(node, dict) else None
    return str(node).strip() if node else None


def _top(raw: dict, side: str, n: int = 3) -> list[dict]:
    rows = ((raw.get("data") or {}).get("broker_summary") or {}).get(side) or []
    out = []
    for b in rows[:n]:
        code = b.get("netbs_broker_code") or b.get("broker_code") or b.get("code")
        val = b.get("bval") if side == "brokers_buy" else b.get("sval")
        try:
            val = abs(float(str(val).replace(",", ""))) / 1e9
        except (TypeError, ValueError):
            val = None
        out.append(
            {
                "code": code,
                "value_bn": round(val, 1) if val is not None else None,
                "type": b.get("type"),
            }
        )
    return out


def label(accdist: str | None) -> str:
    a = (accdist or "").lower()
    return "bull" if a in BULL else "bear" if a in BEAR else "neutral" if a else "na"


def _window(end: date) -> str:
    dates = [d for d in history_dates() if d <= end]
    return str(dates[-WINDOW] if len(dates) >= WINDOW else dates[0])


async def _collect(tickers: list[str], end: date) -> dict:
    from pulse.core.data.stockbit import StockbitClient

    client = StockbitClient()
    if not client.is_authenticated or not client.get_token_status()["is_valid"]:
        raise RuntimeError(
            "Token Stockbit tidak ada / kedaluwarsa. Perbarui file token lalu coba lagi."
        )
    sessions = [d for d in history_dates() if d <= end]
    start = _window(end)
    last = str(end)
    # Stockbit publishes a session's broker summary some time after the close: use the
    # latest session that already has data for the "1 day" view.
    probe = await client.fetch_broker_summary(tickers[0], last, last)
    if not probe or not (probe.raw_data or {}).get("data", {}).get("bandar_detector"):
        last = str(sessions[-2]) if len(sessions) > 1 else last
    out = {}
    for i, t in enumerate(tickers):
        row = {"code": t}
        for key, s, e in (("d1", last, last), ("d20", start, str(end))):
            summ = await client.fetch_broker_summary(t, s, e)
            await asyncio.sleep(PAUSE_S)
            if not summ or not (summ.raw_data or {}).get("data", {}).get("bandar_detector"):
                continue
            raw = summ.raw_data or {}
            row[f"accdist_{key}"] = _accdist(raw, "data", "bandar_detector", "broker_accdist")
            row[f"top5_{key}"] = _accdist(raw, "data", "bandar_detector", "top5", "accdist")
            if summ.bandar:
                row[f"top5_pct_{key}"] = summ.bandar.top5_percent
            if key == "d20":
                row["buyers_20d"] = _top(raw, "brokers_buy")
                row["sellers_20d"] = _top(raw, "brokers_sell")
        row["label"] = label(row.get("top5_d20") or row.get("accdist_d20"))
        out[t] = row
        if (i + 1) % 10 == 0:
            log.info(f"Broker flow {i + 1}/{len(tickers)}")
    return {"end": str(end), "start_20d": start, "d1_date": last, "brokers": out}


def collect(tickers: list[str], end: date) -> Path:
    data = asyncio.run(_collect(tickers, end))
    BROKER_DIR.mkdir(parents=True, exist_ok=True)
    path = BROKER_DIR / f"broker_{end:%Y%m%d}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load(on: str) -> dict | None:
    """Broker flow file for a price date (YYYY-MM-DD), or None."""
    path = BROKER_DIR / f"broker_{on.replace('-', '')}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
