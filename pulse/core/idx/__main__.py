"""Batch entry point, e.g. for a scheduled task after 17:00 WIB.

python -m pulse.core.idx update          # gabungkan file Excel IDX baru ke histori
python -m pulse.core.idx ownership       # ambil ulang free float BEI & KSEI (bulanan)
python -m pulse.core.idx universe [70]   # bangun ulang universe big cap
python -m pulse.core.idx ihsgx           # IHSG vs IHSG ex-HSC
python -m pulse.core.idx swing [TICKER]  # screener swing / analisa satu saham
python -m pulse.core.idx backtest [--nofilter]
python -m pulse.core.idx dashboard [--open]  # bangun data/reports/dashboard.html
python -m pulse.core.idx daily [--open]  # ingest + update + ihsgx + swing + dashboard
python -m pulse.core.idx ingest            # proses bundel pulse_idx_*.json dari folder Downloads
python -m pulse.core.idx universe --force  # susun ulang di luar jadwal kunci bulanan
python -m pulse.core.idx broker             # broker flow 70 big cap (token Stockbit milik pengguna)
python -m pulse.core.idx artifact-export   # salin dashboard lokal -> data/reports/artifact/*.json
"""

import sys

from pulse.core.idx import swing
from pulse.core.idx.benchmark import build_ihsg_ex_hsc, format_benchmark
from pulse.core.idx.dashboard import build_dashboard
from pulse.core.idx.ownership import fetch_ownership
from pulse.core.idx.prices import PriceDownloadError
from pulse.core.idx.summary import update_history
from pulse.core.idx.universe import UniverseRules, build_universe, format_universe


def _swing(args: list[str]) -> str:
    params = swing.SwingParams(market_filter="--nofilter" not in args)
    ind, bench, mcap = swing.load_market(params)
    if args and args[0] == "backtest":
        return swing.format_backtest(swing.backtest(ind, mcap, bench, params))
    snap = swing.screen(ind, swing.current_universe(), params)
    tickers = [a for a in args if not a.startswith("-")]
    return swing.format_ticker(tickers[0].upper(), snap) if tickers else swing.format_screen(snap)


def _broker() -> str:
    from pulse.core.idx.brokerflow import collect
    from pulse.core.idx.summary import latest_summary
    from pulse.core.idx.universe import load_universe

    try:
        path = collect(load_universe()["tickers"], latest_summary().date.iloc[0].date())
        return f"Broker flow: {path}"
    except Exception as e:  # noqa: BLE001 - token habis / jaringan: dashboard tetap dibangun
        return f"Broker flow dilewati: {e}"


def _monthly_lock() -> None:
    """Renew the universe once a month (last weekday); otherwise leave it locked."""
    from pulse.core.idx.summary import latest_summary
    from pulse.core.idx.universe import rebuild_due

    if rebuild_due(latest_summary().date.iloc[0].date()):
        u = build_universe(UniverseRules(), refresh_ownership=True)
        print(f"Kunci bulanan: universe disusun ulang per {u['as_of']} ({len(u['tickers'])} saham)")


def main(argv: list[str]) -> None:
    cmd, args = (argv[0], argv[1:]) if argv else ("daily", [])
    if cmd in ("ingest", "daily"):
        from pulse.core.idx.ingest import ingest

        report = ingest()
        if report:
            print(report)
    if cmd in ("update", "daily"):
        hist = update_history()
        if len(hist):
            print(
                f"Histori IDX: {hist.date.nunique()} hari bursa, terakhir {hist.date.max().date()}"
            )
    if cmd == "ownership":
        df = fetch_ownership()
        print(f"Ownership tersimpan: {len(df)} emiten")
    elif cmd == "universe":
        from pulse.core.idx.summary import latest_summary
        from pulse.core.idx.universe import load_universe, rebuild_due

        nums = [a for a in args if a.isdigit()]
        size = int(nums[0]) if nums else 70
        if "--force" in args or rebuild_due(latest_summary().date.iloc[0].date()):
            u = build_universe(UniverseRules(size=size), refresh_ownership=True)
        else:
            u = load_universe()
            print(f"Universe terkunci (snapshot {u['as_of']}); kunci berikutnya di akhir bulan.\n")
        print(format_universe(u))
    elif cmd == "ihsgx":
        print(format_benchmark(build_ihsg_ex_hsc(refresh=True)))
    elif cmd == "swing":
        print(_swing(args))
    elif cmd == "backtest":
        print(_swing(["backtest", *args]))
    elif cmd == "artifact-export":
        from pulse.core.idx.artifact_export import export

        m = export()
        print(f"Ekspor dari dashboard lokal (harga s/d {m['price_date']}):")
        for k, v in m["datasets"].items():
            print(f"  {k:<10} {v['rows']:>6} baris  {v['kb']:>7} KB")
    elif cmd == "dashboard":
        print(f"Dashboard: {build_dashboard(open_browser='--open' in args)}")
    elif cmd == "broker":
        print(_broker())
    elif cmd == "daily":
        _monthly_lock()
        print(_broker())
        print(format_benchmark(build_ihsg_ex_hsc(refresh=True)))
        print()
        print(_swing([]))
        print(f"\nDashboard: {build_dashboard(open_browser='--open' in args, update=False)}")
    elif cmd not in ("update", "ingest"):
        print(__doc__)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except PriceDownloadError as e:
        print(f"\nGAGAL mengambil harga: {e}")
        sys.exit(1)
