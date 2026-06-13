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
