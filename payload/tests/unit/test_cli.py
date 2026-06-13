"""Unit tests for the operator CLI (REQ-OPS-03)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdgs.cli.main import main


def test_status_command_returns_zero(tmp_path: Path) -> None:
    db = str(tmp_path / "cat.sqlite")
    assert main(["status", "--db", db]) == 0


def test_default_command_is_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Isolate the default catalogue path under a temp data dir.
    monkeypatch.setenv("PDGS_DATA_DIR", str(tmp_path / "data"))
    assert main([]) == 0


def test_status_lists_empty_catalogue(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = str(tmp_path / "cat.sqlite")
    main(["status", "--db", db])
    out = capsys.readouterr().out
    assert "empty" in out


def test_ingest_then_status_lists_products(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = str(tmp_path / "cat.sqlite")
    # ingest writes downloads under the default data dir; isolate it.
    monkeypatch.setenv("PDGS_DATA_DIR", str(tmp_path / "data"))
    assert main(["ingest", "--db", db]) == 0
    capsys.readouterr()  # drain ingest output
    assert main(["status", "--db", db]) == 0
    out = capsys.readouterr().out
    assert "l1_rbt_synthetic" in out
    assert "l2_wst_synthetic" in out


def _fixture_config_path() -> str:
    return str(Path(__file__).resolve().parents[2] / "config" / "fixture.toml")


def test_process_command_writes_and_registers_then_status(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db = str(tmp_path / "cat.sqlite")
    out_dir = str(tmp_path / "derived")
    rc = main(["process", "--config", _fixture_config_path(), "--db", db, "--out", out_dir])
    assert rc == 0
    proc_out = capsys.readouterr().out
    assert "L2_DERIVED" in proc_out
    assert "out-of-range" in proc_out

    assert main(["status", "--db", db]) == 0
    status_out = capsys.readouterr().out
    assert "SST_L2_DERIVED" in status_out
    assert "PROCESSED" in status_out


def test_process_missing_l1_returns_error(tmp_path: Path) -> None:
    db = str(tmp_path / "cat.sqlite")
    rc = main(
        [
            "process",
            "--config",
            _fixture_config_path(),
            "--db",
            db,
            "--l1",
            str(tmp_path / "nope"),
            "--out",
            str(tmp_path / "derived"),
        ]
    )
    assert rc == 1


# --- enriched status (REQ-OPS-03) ------------------------------------------


def test_status_shows_config_version_for_derived(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db = str(tmp_path / "cat.sqlite")
    out_dir = str(tmp_path / "derived")
    assert main(["process", "--config", _fixture_config_path(), "--db", db, "--out", out_dir]) == 0
    capsys.readouterr()  # drain process output
    assert main(["status", "--db", db]) == 0
    out = capsys.readouterr().out
    # The derived product's provenance config_version is surfaced per row.
    assert "config=fixture-1.0.0" in out


def test_status_filter_by_type(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = str(tmp_path / "cat.sqlite")
    monkeypatch.setenv("PDGS_DATA_DIR", str(tmp_path / "data"))
    assert main(["ingest", "--db", db]) == 0
    capsys.readouterr()
    assert main(["status", "--db", db, "--type", "SL_1_RBT"]) == 0
    out = capsys.readouterr().out
    assert "l1_rbt_synthetic" in out
    assert "l2_wst_synthetic" not in out
    assert "type=SL_1_RBT" in out


def test_status_filter_by_status_no_match(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = str(tmp_path / "cat.sqlite")
    monkeypatch.setenv("PDGS_DATA_DIR", str(tmp_path / "data"))
    assert main(["ingest", "--db", db]) == 0
    capsys.readouterr()
    assert main(["status", "--db", db, "--status", "FAILED"]) == 0
    out = capsys.readouterr().out
    assert "no matching product" in out


def test_status_invalid_status_filter_errors(tmp_path: Path) -> None:
    db = str(tmp_path / "cat.sqlite")
    with pytest.raises(SystemExit):
        main(["status", "--db", db, "--status", "BOGUS"])


# --- dead-letter inspection (REQ-OPS-01) -----------------------------------


def test_dead_letter_empty_message(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db = str(tmp_path / "cat.sqlite")
    assert main(["dead-letter", "--db", db]) == 0
    out = capsys.readouterr().out
    assert "No dead-lettered products." in out


def test_dead_letter_lists_failed_product(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from datetime import UTC, datetime

    from pdgs.catalogue.models import Product, ProductStatus
    from pdgs.catalogue.repository import SqliteCatalogue

    db = str(tmp_path / "cat.sqlite")
    cat = SqliteCatalogue(db)
    now = datetime(2024, 6, 1, tzinfo=UTC)
    cat.register(
        Product(
            product_id="broken-l1",
            collection_id="EO:EUM:DAT:0411",
            product_type="SL_1_RBT",
            level="L1",
            timeliness="NTC",
            sensing_start=now,
            sensing_end=now,
            bbox=None,
            local_path="",
            checksum="",
            size_bytes=0,
            status=ProductStatus.FAILED,
            provenance=None,
            created_at=now,
            updated_at=now,
        )
    )
    assert main(["dead-letter", "--db", db]) == 0
    out = capsys.readouterr().out
    assert "broken-l1" in out
    assert "dead-lettered product(s)" in out


# --- on-demand reprocessing (REQ-OPS-02) -----------------------------------


def test_reprocess_unknown_id_returns_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db = str(tmp_path / "cat.sqlite")
    rc = main(["reprocess", "nope", "--config", _fixture_config_path(), "--db", db])
    assert rc == 1
    out = capsys.readouterr().out
    assert "ERROR" in out


def test_reprocess_refreshes_derived_in_place(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = str(tmp_path / "cat.sqlite")
    monkeypatch.setenv("PDGS_DATA_DIR", str(tmp_path / "data"))
    assert main(["ingest", "--db", db]) == 0
    out_dir = str(tmp_path / "derived")
    assert main(["process", "--config", _fixture_config_path(), "--db", db, "--out", out_dir]) == 0
    capsys.readouterr()

    rc = main(
        [
            "reprocess",
            "l1_rbt_synthetic__SST_L2_DERIVED",
            "--config",
            _fixture_config_path(),
            "--db",
            db,
            "--out",
            str(tmp_path / "derived2"),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "source L1:   l1_rbt_synthetic" in out
    assert "refreshed in place" in out


# --- one-command end-to-end run --------------------------------------------


def test_run_end_to_end_passes_on_fixtures(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = str(tmp_path / "cat.sqlite")
    monkeypatch.setenv("PDGS_DATA_DIR", str(tmp_path / "data"))
    rc = main(
        ["run", "--config", _fixture_config_path(), "--db", db, "--out", str(tmp_path / "out")]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "RUN COMPLETE" in out
    assert "Validation verdict: PASS" in out
    # A validation report was produced under the data root.
    reports = list((tmp_path / "data" / "reports").rglob("validation.json"))
    assert reports, "expected a validation.json report from the run"
