"""Unit tests for the operator CLI (REQ-OPS-03)."""

from pdgs.cli.main import main


def test_status_command_returns_zero() -> None:
    assert main(["status"]) == 0


def test_default_command_is_status() -> None:
    assert main([]) == 0
