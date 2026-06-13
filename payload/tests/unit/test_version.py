"""Unit tests for provenance/version stamping (REQ-CFG-02)."""

from pdgs import __version__
from pdgs.config.version import current_stamp


def test_current_stamp_matches_processor_version() -> None:
    stamp = current_stamp()
    assert stamp.processor_version == __version__


def test_current_stamp_has_config_version() -> None:
    stamp = current_stamp()
    assert stamp.config_version
