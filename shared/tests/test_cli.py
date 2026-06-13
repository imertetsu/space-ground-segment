"""Unit tests (no DB) for the dark-flagged ``sgs-ops`` CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sgs_shared.cli.main import DARK_FLAG_ENV, DARK_MESSAGE, main

if TYPE_CHECKING:
    import pytest


def test_status_dark_flag_off_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(DARK_FLAG_ENV, raising=False)
    rc = main(["status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert DARK_MESSAGE in out
    assert "dark" in out


def test_status_dark_flag_empty_is_off(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(DARK_FLAG_ENV, "")
    rc = main(["status"])
    assert rc == 0
    assert DARK_MESSAGE in capsys.readouterr().out


def test_seed_demo_dark_flag_off_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The hidden seed-demo command is also gated by the dark flag (no DB touched).
    monkeypatch.delenv(DARK_FLAG_ENV, raising=False)
    rc = main(["seed-demo"])
    assert rc == 0
    assert DARK_MESSAGE in capsys.readouterr().out
