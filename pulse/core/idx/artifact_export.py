"""Mirror the finished local dashboard into datasets for a shared claude.ai Dashboard artifact.

The artifact never fetches or recomputes anything: it only copies the DATA JSON that is
embedded in data/reports/dashboard.html after the local daily update. Run

    python -m pulse.core.idx artifact-export

after `daily`, then upload the JSON files in data/reports/artifact/ and artifact_page.html.
"""

import json
from datetime import datetime
from pathlib import Path

from pulse.core.idx import DATA_DIR
from pulse.core.idx.dashboard import DASHBOARD_FILE

EXPORT_DIR = DATA_DIR / "reports" / "artifact"
PAGE_FILE = Path(__file__).with_name("artifact_page.html")

FACTORS = ("stage", "rs13", "cmf", "vwap", "foreign", "big_lot")


def read_local_dashboard(path: Path = DASHBOARD_FILE) -> dict:
    """The DATA object embedded in the local dashboard HTML."""
    html = path.read_text(encoding="utf-8")
    start = html.index("const DATA = ") + len("const DATA = ")
    end = html.index(";\n", start)
    return json.loads(html[start:end].replace("<\\/", "</"))


def _screener_row(r: dict) -> dict:
    f = r.get("fund") or {}
    row = {
        k: r.get(k)
        for k in (
            "code",
            "name",
            "sector",
            "setup",
            "score",
            "close",
            "chg1d",
            "mcap_t",
            "rs4",
            "rs13",
            "rsi",
            "vol_ratio",
            "to_hh55",
            "atr_pct",
            "stop",
            "tp1",
            "tp2",
            "risk_pct",
            "stage",
            "stage_days",
            "stage_start",
            "cmf",
            "vwap",
            "foreign_pct",
            "foreign_days",
            "foreign_net5_bn",
            "foreign_today_bn",
            "big_lot",
            "nonreg_pct",
            "bull",
            "bear",
        )
    }
    row["hh55"] = (r.get("spark") or {}).get("hh55")
    for k in FACTORS:
        row[f"lb_{k}"] = (r.get("labels") or {}).get(k)
    for k in (
        "pe",
        "pbv",
        "roe",
        "ni_growth",
        "rev_growth",
        "net_margin",
        "der",
        "ocf_ni",
        "ni_ttm_bn",
    ):
        row[k] = f.get(k)
    row["fund_report"] = f.get("report")
    row["fund_type"] = f.get("report_type")
    row["fund_currency"] = f.get("currency")
    row["bank"] = f.get("bank")
    row["flags"] = "; ".join(f.get("flags") or [])
    return row


def build_datasets(data: dict) -> dict[str, tuple[list[dict], str, str]]:
    """{dataset_id: (rows, title, description)} from the local dashboard DATA."""
    m, b, bt = data["meta"], data["bench"], data["backtest"]
    rules = m.get("universe_rules") or {}
    market = [
        {
            "price_date": m["price_date"],
            "idx_file_date": m["idx_file_date"],
            "idx_days": m["idx_days"],
            "generated": m["generated"],
            "market_ok": m["market_ok"],
            "exhsc": m["exhsc"],
            "exhsc_ma50": m["exhsc_ma50"],
            "hsc_weight": m["hsc_weight"],
            "hsc_count": m["hsc_count"],
            "hsc_as_of": m["hsc_as_of"],
            "ksei_snapshot": m.get("ksei_snapshot"),
            "universe_as_of": m["universe_as_of"],
            "universe_n": len(data["rows"]),
            "min_ff_ksei": rules.get("min_ff_ksei"),
            "min_avg_value_bn": rules.get("min_avg_value_bn"),
            "fund_generated": m.get("fund_generated"),
            "usd_idr": m.get("usd_idr"),
        }
    ]
    perf = [
        {
            "period": p,
            "ihsg": v["ihsg"],
            "exhsc": v["exhsc"],
            "diff": None
            if v["ihsg"] is None or v["exhsc"] is None
            else round(v["exhsc"] - v["ihsg"], 2),
        }
        for p, v in b["perf"].items()
    ]
    bench = [
        {"date": d, "ihsg": i, "exhsc": e} for d, i, e in zip(b["dates"], b["ihsg"], b["exhsc"])
    ]
    spark = [
        {"code": r["code"], "date": d, "close": c, "ma50": a}
        for r in data["rows"]
        for d, c, a in zip(r["spark"]["dates"], r["spark"]["close"], r["spark"]["ma50"])
    ]
    sectors = [
        {
            "sector": s["sector"],
            "n": s["n"],
            "quadrant": s["quadrant"],
            "ret20": s["ret20"],
            "step": i,
            "x": x,
            "y": y,
            "last": i == len(s["trail"]) - 1,
        }
        for s in data["sectors"]
        for i, (x, y) in enumerate(s["trail"])
    ]
    foreign = [
        {"side": side, "code": x["code"], "net_bn": x["net_bn"], "value_bn": x["value_bn"]}
        for side in ("buy", "sell")
        for x in data["foreign_today"][side]
    ]
    events = [
        {
            "n": i,
            "date": e["date"],
            "code": e["code"],
            "category": e["category"],
            "label": e["label"],
            "title": e["title"],
            "url": e.get("url"),
        }
        for i, e in enumerate(data.get("events") or [])
    ]
    st = bt["stats"]
    bt_stats = [
        {
            **st,
            "start": bt["dates"][0],
            "end": bt["dates"][-1],
            "exhsc_total": round(bt["exhsc"][-1] / 100 - 1, 4) if bt["exhsc"][-1] else None,
        }
    ]
    bt_equity = [
        {"date": d, "equity": q, "exhsc": e, "ihsg": i}
        for d, q, e, i in zip(bt["dates"], bt["equity"], bt["exhsc"], bt["ihsg"])
    ]
    bt_trades = [{"n": i, **t} for i, t in enumerate(bt["recent"])]

    src = f"Salinan dashboard lokal Pulse (harga s/d {m['price_date']}, file IDX {m['idx_file_date']})."
    return {
        "market": (
            market,
            "Status pasar & data",
            "Status IHSG ex-HSC vs MA50, tanggal data dan aturan universe. " + src,
        ),
        "perf": (
            perf,
            "IHSG vs ex-HSC per periode",
            "Return IHSG dan IHSG ex-HSC (%) per periode. " + src,
        ),
        "bench": (
            bench,
            "IHSG vs ex-HSC 1 tahun",
            "IHSG dan IHSG ex-HSC harian, basis 100. " + src,
        ),
        "screener": (
            [_screener_row(r) for r in data["rows"]],
            "Screener 70 big cap",
            "Setup swing, faktor, level SL/TP dan fundamental per saham. " + src,
        ),
        "spark": (
            spark,
            "Harga 120 hari per saham",
            "Close dan MA50 harian per saham untuk grafik detail. " + src,
        ),
        "sectors": (
            sectors,
            "Rotasi sektor (RRG)",
            "RS-Ratio dan RS-Momentum per sektor vs IHSG ex-HSC, jejak 5 minggu. " + src,
        ),
        "foreign": (
            foreign,
            "Asing hari ini",
            "Net beli/jual asing terbesar (Rp miliar) di universe. " + src,
        ),
        "events": (
            events,
            "Keterbukaan informasi",
            "Pengumuman penting emiten 45 hari terakhir dari idx.co.id. " + src,
        ),
        "bt_stats": (
            bt_stats,
            "Ringkasan backtest",
            "Statistik backtest Relative-Strength Breakout. " + src,
        ),
        "bt_equity": (
            bt_equity,
            "Kurva backtest",
            "Ekuitas strategi vs IHSG dan ex-HSC, basis 100, mingguan. " + src,
        ),
        "bt_trades": (bt_trades, "Trade backtest terakhir", "12 trade simulasi terakhir. " + src),
    }


def export(path: Path = DASHBOARD_FILE, out_dir: Path = EXPORT_DIR) -> dict:
    """Write one JSON per dataset plus manifest.json; returns the manifest."""
    data = read_local_dashboard(path)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "exported": datetime.now().isoformat(timespec="seconds"),
        "price_date": data["meta"]["price_date"],
        "datasets": {},
    }
    for ds_id, (rows, title, desc) in build_datasets(data).items():
        file = out_dir / f"{ds_id}.json"
        file.write_text(
            json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        manifest["datasets"][ds_id] = {
            "file": file.name,
            "rows": len(rows),
            "title": title,
            "description": desc,
            "kb": round(file.stat().st_size / 1024, 1),
        }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest
