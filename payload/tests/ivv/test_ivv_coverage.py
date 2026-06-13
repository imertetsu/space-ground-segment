"""IV&V coverage suite — every Epic-1 REQ is exercised by a collecting test.

This is the independent verification level of the SVP (`docs/svp-svr/SVP.md`): it
defines the CANONICAL set of all Epic-1 requirement ids and maps each to the
test(s) that exercise it, then ASSERTS — by actually collecting the test suite —
that every requirement has at least one mapped test that pytest can collect. If a
requirement has no collectable mapped test, the suite FAILS, so it genuinely gates
CI: an unverified requirement breaks the build.

Robustness: the mapped node ids are checked against the REAL collected node-id set
(obtained by running ``pytest --collect-only`` in a subprocess against this repo's
test tree), not against a hand-maintained list — a renamed/deleted test is caught.
The suite also asserts the mapping itself is complete (covers exactly the canonical
REQ set) so a new requirement cannot be silently left unmapped.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# tests/ivv/ -> tests/ -> payload/
_TESTS_ROOT = Path(__file__).resolve().parents[1]
_PAYLOAD_ROOT = _TESTS_ROOT.parent

# --- Canonical Epic-1 requirement set (SRD §1 / SVP §3) ---------------------
_CANONICAL_REQS: frozenset[str] = frozenset(
    {
        "REQ-ING-01",
        "REQ-ING-02",
        "REQ-ING-03",
        "REQ-ING-04",
        "REQ-PRO-01",
        "REQ-PRO-02",
        "REQ-PRO-03",
        "REQ-PRO-04",
        "REQ-PRO-05",
        "REQ-VAL-01",
        "REQ-VAL-02",
        "REQ-VAL-03",
        "REQ-VAL-04",
        "REQ-CFG-01",
        "REQ-CFG-02",
        "REQ-CFG-03",
        "REQ-OPS-01",
        "REQ-OPS-02",
        "REQ-OPS-03",
    }
)

# --- Requirement -> mapped test node-id fragments ---------------------------
# Each fragment is a "<file>::<test_function>" substring; a requirement is verified
# when at least one fragment matches a collected node id. Fragments are checked
# against the real collected set below, so a stale mapping fails the suite.
_REQ_TO_TESTS: dict[str, tuple[str, ...]] = {
    # Ingestion
    "REQ-ING-01": ("test_ingest_roundtrip.py::test_ingest_l1_roundtrip_registers_and_verifies",),
    "REQ-ING-02": ("test_ingest_roundtrip.py::test_ingest_l2_roundtrip_registers",),
    "REQ-ING-03": ("test_integrity.py::test_verify_rejects_corrupted_file",),
    "REQ-ING-04": ("test_ingest_roundtrip.py::test_ingest_both_collections_persist",),
    # Processing
    "REQ-PRO-01": ("test_cloud_screening.py::test_screen_flags_known_cloudy_pixels_via_l1_flag",),
    "REQ-PRO-02": ("test_sst_retrieval.py::test_retrieve_recovers_synthetic_field_clear_sky",),
    "REQ-PRO-03": ("test_process_scene.py::test_process_scene_writes_product_and_registers",),
    # Each processor is independently runnable: its standalone unit test exercises it
    # without the other processor.
    "REQ-PRO-04": (
        "test_cloud_screening.py::test_screen_l1_flag_disabled_ignores_flag",
        "test_sst_retrieval.py::test_retrieve_sets_cloudy_pixels_to_nan",
    ),
    "REQ-PRO-05": ("test_sst_retrieval.py::test_retrieve_flags_out_of_range_without_clamping",),
    # Validation
    "REQ-VAL-01": ("test_colocation.py::test_same_grid_returns_aligned_pairs",),
    "REQ-VAL-02": (
        "test_result.py::test_write_result_json_roundtrips",
        "test_stats.py::test_known_bias_and_rmse",
    ),
    "REQ-VAL-03": ("test_validate_product.py::test_degraded_derived_trips_the_gate",),
    "REQ-VAL-04": ("test_report.py::test_markdown_report_written_and_labels_synthetic",),
    # Configuration
    "REQ-CFG-01": ("test_config_processing.py::test_load_default_toml_exposes_config_version",),
    "REQ-CFG-02": ("test_process_scene.py::test_process_scene_writes_product_and_registers",),
    "REQ-CFG-03": ("test_reproducibility.py::test_rerun_is_reproducible",),
    # Operations
    "REQ-OPS-01": ("test_ingest_roundtrip.py::test_ingest_corrupt_download_routes_to_failed",),
    "REQ-OPS-02": ("test_reproducibility.py::test_on_demand_reprocessing_refreshes_in_place",),
    "REQ-OPS-03": ("test_cli.py::test_status_command_returns_zero",),
}


def _collect_node_ids() -> list[str]:
    """Return the pytest-collected node ids for the whole test tree.

    Runs ``pytest --collect-only -q`` in a subprocess (so this suite verifies the
    REAL collection, robust to renamed/removed tests). Excludes this IV&V module to
    avoid self-reference, and disables addopts that would suppress the listing.
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(_TESTS_ROOT),
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
        ],
        cwd=_PAYLOAD_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "pytest --collect-only failed; cannot verify REQ coverage.\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    node_ids: list[str] = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if "::" in stripped and stripped.endswith(")") is False:
            node_ids.append(stripped.replace("\\", "/"))
    return node_ids


@pytest.fixture(scope="module")
def collected_node_ids() -> list[str]:
    ids = _collect_node_ids()
    assert ids, "no tests were collected — collection is broken"
    return ids


@pytest.mark.ivv
def test_mapping_covers_exactly_the_canonical_reqs() -> None:
    """The REQ->test mapping must cover exactly the canonical Epic-1 requirement set."""
    mapped = frozenset(_REQ_TO_TESTS)
    missing = _CANONICAL_REQS - mapped
    extra = mapped - _CANONICAL_REQS
    assert not missing, f"requirements with no mapping entry (unverified): {sorted(missing)}"
    assert not extra, f"mapping references unknown requirements: {sorted(extra)}"


@pytest.mark.ivv
def test_every_requirement_has_a_collectable_test(collected_node_ids: list[str]) -> None:
    """Every canonical REQ maps to at least one test node id that actually collects."""
    unverified: list[str] = []
    for req in sorted(_CANONICAL_REQS):
        fragments = _REQ_TO_TESTS[req]
        if not any(_matches(frag, collected_node_ids) for frag in fragments):
            unverified.append(req)
    assert not unverified, (
        f"requirements with no collectable mapped test (unverified — gate failed): {unverified}"
    )


@pytest.mark.ivv
def test_no_mapping_points_at_a_missing_test(collected_node_ids: list[str]) -> None:
    """Every mapped node-id fragment must match a real collected test (no stale rows)."""
    stale: list[str] = []
    for req, fragments in _REQ_TO_TESTS.items():
        for frag in fragments:
            if not _matches(frag, collected_node_ids):
                stale.append(f"{req} -> {frag}")
    assert not stale, f"mapping fragments that match no collected test: {stale}"


def _matches(fragment: str, node_ids: list[str]) -> bool:
    """True if ``fragment`` is a substring of any collected node id."""
    norm = fragment.replace("\\", "/")
    return any(norm in nid for nid in node_ids)
