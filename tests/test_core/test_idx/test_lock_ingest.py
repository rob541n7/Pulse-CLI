"""Monthly universe lock, one-shot ingest, HSC risk and pullback signal."""

import json
from datetime import date

import pandas as pd
import pytest

from pulse.core.idx import ingest, summary, universe
from pulse.core.idx.factors import hsc_risk
from pulse.core.idx.swing import pullback_signal


@pytest.fixture
def snap_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(universe, "SNAPSHOT_DIR", tmp_path / "snapshots")
    return tmp_path / "snapshots"


def test_rebuild_due_once_a_month(snap_dir):
    assert universe.rebuild_due(date(2026, 11, 11))  # belum ada snapshot
    universe.save_snapshot({"as_of": "2026-10-30", "tickers": []})
    assert not universe.rebuild_due(date(2026, 10, 30))
    assert not universe.rebuild_due(date(2026, 11, 11))
    assert not universe.rebuild_due(date(2026, 11, 27))  # Jumat, Senin masih November
    assert universe.rebuild_due(date(2026, 11, 30))  # hari kerja terakhir bulan
    assert universe.rebuild_due(date(2026, 12, 1))  # terlewat -> susun saat itu
    universe.save_snapshot({"as_of": "2026-11-30", "tickers": []})
    assert not universe.rebuild_due(date(2026, 12, 1))
    assert [s["as_of"] for s in universe.snapshots()] == ["2026-10-30", "2026-11-30"]


def test_eligible_shares_filters_ff_hsc_delisting():
    own = pd.DataFrame(
        {
            "code": ["AAAA", "BBBB", "CCCC", "DDDD"],
            "ff_ksei": [30.0, 5.0, 40.0, 50.0],
            "ff_status": ["Memenuhi", "Memenuhi", "Memenuhi", "Force Delisting"],
        }
    )
    shares = pd.Series({"AAAA": 100.0, "BBBB": 100.0, "CCCC": 100.0, "DDDD": 100.0})
    assert universe.eligible_shares(own, {"CCCC"}, shares, 12.5) == {"AAAA": 100.0}


@pytest.mark.parametrize(
    ("holders", "ff", "risk"),
    [
        (2, 12.73, "mungkin"),  # CBDK: 87,27% di 2 pemegang, 8 slot < 1% cukup
        (4, 58.0, "rendah"),
        (6, 0.07, "tinggi"),  # 99,93% di 6 pemegang
        (10, 12.0, "rendah"),  # 10 besar sudah diketahui = 88%
        (None, None, "na"),
    ],
)
def test_hsc_risk(holders, ff, risk):
    assert hsc_risk(holders, ff)["hsc_risk"] == risk


def test_hsc_risk_need_per_slot():
    r = hsc_risk(2, 11.71)  # 88,29% diketahui, 8 slot kosong
    assert r["hsc_known"] == pytest.approx(88.29)
    assert r["hsc_need"] == pytest.approx((92.5 - 88.29) / 8, abs=0.01)


def test_json_summary_matches_excel_columns(tmp_path, monkeypatch):
    row = {
        "StockCode": " bbca ",
        "StockName": "Bank Central Asia Tbk.",
        "Close": 5325,
        "ListedShares": 1000,
        "ForeignBuy": 70,
        "ForeignSell": 50,
        "Volume": 10,
        "Value": 53250,
        "DelistingDate": "",
    }
    path = tmp_path / "Ringkasan Saham-20261111.json"
    path.write_text(json.dumps([row]), encoding="utf-8")
    df = summary.parse_summary_file(path)
    r = df.iloc[0]
    assert (r.code, r.close, r.market_cap, r.foreign_net) == ("BBCA", 5325, 5_325_000, 20)
    assert str(r.date.date()) == "2026-11-11"

    # Excel menang atas JSON untuk tanggal yang sama; urutan menurut tanggal
    monkeypatch.setattr(summary, "IDX_DIR", tmp_path)
    (tmp_path / "Ringkasan Saham-20261111.xlsx").write_bytes(b"")
    (tmp_path / "Ringkasan Saham-20261110.json").write_text("[]", encoding="utf-8")
    assert [p.name for p in summary.summary_files()] == [
        "Ringkasan Saham-20261110.json",
        "Ringkasan Saham-20261111.xlsx",
    ]


def test_apply_hsc_adds_removes_and_flags_unparsed(tmp_path, monkeypatch):
    hsc_file = tmp_path / "hsc.json"
    hsc_file.write_text(
        json.dumps(
            {
                "as_of": "2026-11-06",
                "tickers": ["AAAA", "BBBB"],
                "events": [{"code": "BBBB", "action": "pengenaan", "date": "2026-11-06"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ingest, "HSC_FILE", hsc_file)
    head = "Kepemilikan Saham Terkonsentrasi Tinggi PT"
    out = ingest.apply_hsc(
        [
            {"description": f"Pengenaan {head} B Tbk (BBBB)", "date": "2026-11-06T12:00:00"},
            {"description": f"Pengenaan {head} C Tbk (CCCC)\n", "date": "2026-11-12T12:00:00"},
            {"description": f"Pencabutan {head} A Tbk (AAAA)", "date": "2026-11-13T12:00:00"},
            {
                "description": "Pengumuman Daftar Saham HSC Metodologi Baru",
                "date": "2026-11-13T12:00:00",
            },
        ]
    )
    data = json.loads(hsc_file.read_text(encoding="utf-8"))
    assert out["added"] == ["CCCC"] and out["removed"] == ["AAAA"]
    assert data["tickers"] == ["BBBB", "CCCC"] and data["as_of"] == "2026-11-13"
    assert len(data["events"]) == 3
    assert [u["date"] for u in out["unparsed"]] == ["2026-11-13"]
    # dijalankan ulang: tidak ada perubahan ganda
    assert (
        ingest.apply_hsc([{"description": f"Pengenaan {head} C Tbk (CCCC)", "date": "2026-11-12"}])[
            "added"
        ]
        == []
    )


def test_append_ihsg_only_new_dates(tmp_path, monkeypatch):
    f = tmp_path / "ihsg_official.csv"
    f.write_text("date,close\n2026-11-10,5125.726\n", encoding="utf-8")
    monkeypatch.setattr(ingest, "IHSG_OFFICIAL_FILE", f)
    assert ingest.append_ihsg({"2026-11-10": 5125.726, "2026-11-11": 5115.035}) == ["2026-11-11"]
    assert f.read_text(encoding="utf-8").splitlines()[-1] == "2026-11-11,5115.035"
    assert ingest.append_ihsg({"2026-11-11": 5115.035}) == []


def test_pullback_signal_needs_uptrend_and_cooled_rsi():
    idx = pd.date_range("2026-01-01", periods=1)
    base = {
        "close": 100.0,
        "ma20": 99.0,
        "ma50": 95.0,
        "ma100": 90.0,
        "atr": 4.0,
        "rs13": 0.1,
        "rsi": 50.0,
    }
    cases = {"OK": {}, "HOT": {"rsi": 70.0}, "FAR": {"close": 110.0}, "DOWN": {"ma50": 85.0}}
    ind = {
        k: pd.DataFrame({name: [{**base, **over}[k]] for name, over in cases.items()}, index=idx)
        for k in base
    }
    assert pullback_signal(ind).iloc[0].to_dict() == {
        "OK": True,
        "HOT": False,
        "FAR": False,
        "DOWN": False,
    }


def test_hsc_risk_cleared_by_official_evaluation():
    r = hsc_risk(2, 12.73, cleared=True)  # estimasi "mungkin", tapi lolos evaluasi resmi BEI
    assert r["hsc_risk"] == "bukan" and r["hsc_known"] == pytest.approx(87.27)
