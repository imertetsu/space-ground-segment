"""Validation orchestration — derived SST vs official L2 end-to-end (REQ-VAL-01..04).

:func:`validate_product` composes the Phase 3 pieces: co-locate the derived SST
against the official :class:`~pdgs.ingestion.readers.L2Reference`
(:func:`~pdgs.validation.colocation.colocate`), compute statistics
(:func:`~pdgs.validation.stats.compute_stats`), apply the acceptance-threshold gate
(:func:`~pdgs.validation.result.evaluate`), persist ``validation.json``, and render
the Markdown report + difference plot under the output reports directory.

It returns the :class:`~pdgs.validation.result.ValidationResult`; the caller (CLI)
turns ``result.passed`` into the process exit code so CI gates on it (REQ-VAL-03).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pdgs.config.processing import ValidationConfig
from pdgs.config.version import PROCESSOR_VERSION
from pdgs.ingestion.readers import L2Reference
from pdgs.processing.product import DerivedSstProduct
from pdgs.validation.colocation import colocate
from pdgs.validation.report import render_difference_plot, render_markdown_report
from pdgs.validation.result import ValidationResult, evaluate, write_result_json
from pdgs.validation.stats import compute_stats


def validate_product(
    derived: DerivedSstProduct,
    reference: L2Reference,
    val_cfg: ValidationConfig,
    out_dir: str | Path,
    *,
    config_version: str | None = None,
    synthetic_inputs: bool = False,
    run_timestamp: datetime | None = None,
) -> ValidationResult:
    """Validate ``derived`` against ``reference`` and write the report (REQ-VAL-01..04).

    Co-locates, computes statistics, gates them against ``val_cfg``, then writes
    ``validation.json``, a difference plot PNG, and a Markdown report under
    ``out_dir``. ``config_version`` (the processing config version) is recorded in
    the result metadata; ``synthetic_inputs`` flags the report as a synthetic
    fixture run (SRD §5). Returns the :class:`ValidationResult` (``passed`` gates CI).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    matchups = colocate(derived, reference, val_cfg)
    stats = compute_stats(matchups, val_cfg)

    result = evaluate(
        stats,
        val_cfg,
        derived_product_id=derived.product_id,
        reference_product_id=reference.product_id,
        processor_version=PROCESSOR_VERSION,
        config_version=config_version or derived.provenance.config_version,
        run_timestamp=run_timestamp or datetime.now(tz=UTC),
        synthetic_inputs=synthetic_inputs,
    )

    write_result_json(result, out)
    plot_path = render_difference_plot(matchups, result, out)
    render_markdown_report(result, plot_path.name, out)

    return result
