"""Processor + config version stamping (REQ-CFG-02).

Every product and report records the processor and configuration versions that
produced it, so a rerun with the same versions is reproducible (REQ-CFG-03).
"""

from __future__ import annotations

from dataclasses import dataclass

from pdgs import __version__

PROCESSOR_VERSION: str = __version__
CONFIG_VERSION: str = "0.0.0"


@dataclass(frozen=True)
class ProvenanceStamp:
    """Versions stamped onto every product/report for reproducibility."""

    processor_version: str
    config_version: str


def current_stamp() -> ProvenanceStamp:
    """Return the provenance stamp for the running processor + configuration."""
    return ProvenanceStamp(
        processor_version=PROCESSOR_VERSION,
        config_version=CONFIG_VERSION,
    )
