"""Human-readable validation report + difference plot (REQ-VAL-04).

Renders, from a :class:`~pdgs.validation.result.ValidationResult`:

* a Markdown report (``validation.md``) — stats table, per-threshold PASS/FAIL,
  overall verdict, and run metadata (processor + config versions, thresholds, run
  timestamp), embedding the difference plot;
* a difference-plot PNG (``difference.png``) — a derived-official difference map
  and a histogram of the differences, rendered with the matplotlib **Agg** backend
  so it works headless / in CI.

When the inputs are the SYNTHETIC offline fixtures the report states so prominently
(SRD §5): a simplification / synthetic result is never presented as operational.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless / CI-safe backend — must precede pyplot import.

import matplotlib.pyplot as plt
import numpy as np

from pdgs.validation.colocation import MatchupSet
from pdgs.validation.result import ValidationResult

_PNG_NAME = "difference.png"
_MD_NAME = "validation.md"


def _verdict(passed: bool) -> str:
    """Return the human verdict string for a boolean pass/fail."""
    return "PASS" if passed else "FAIL"


def _fmt(value: float) -> str:
    """Format a float stat for the report, rendering NaN as ``n/a``."""
    if value != value:  # NaN
        return "n/a"
    return f"{value:.4f}"


def render_difference_plot(
    matchups: MatchupSet,
    result: ValidationResult,
    out_dir: str | Path,
) -> Path:
    """Render the derived-official difference plot PNG; return its path (REQ-VAL-04).

    Produces a two-panel figure: a scatter map of the per-pixel difference (coloured
    by ``derived - official``) and a histogram of the differences. Uses the Agg
    backend (set at import). With no matchups an explanatory placeholder is drawn.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / _PNG_NAME

    fig, (ax_map, ax_hist) = plt.subplots(1, 2, figsize=(11, 4.5))
    title_suffix = " [SYNTHETIC INPUTS]" if result.synthetic_inputs else ""
    fig.suptitle(
        f"Derived - Official SST difference ({result.derived_product_id}){title_suffix}",
        fontsize=11,
    )

    if matchups.count == 0:
        for ax in (ax_map, ax_hist):
            ax.text(0.5, 0.5, "no co-located matchups", ha="center", va="center")
            ax.set_xticks([])
            ax.set_yticks([])
        fig.tight_layout()
        fig.savefig(path, dpi=110)
        plt.close(fig)
        return path

    diff = np.asarray(matchups.derived_k - matchups.reference_k, dtype=np.float64)

    # --- Panel 1: difference map (scatter by geolocation) ---
    span = float(np.max(np.abs(diff))) if diff.size else 1.0
    span = span if span > 0 else 1.0
    scatter = ax_map.scatter(
        matchups.longitudes,
        matchups.latitudes,
        c=diff,
        cmap="coolwarm",
        vmin=-span,
        vmax=span,
        s=12,
    )
    ax_map.set_xlabel("longitude (deg)")
    ax_map.set_ylabel("latitude (deg)")
    ax_map.set_title("difference map (K)")
    fig.colorbar(scatter, ax=ax_map, label="derived - official (K)")

    # --- Panel 2: histogram of differences ---
    ax_hist.hist(diff, bins=30, color="#4C72B0", edgecolor="white")
    ax_hist.axvline(0.0, color="black", linewidth=0.8)
    ax_hist.axvline(
        result.stats.bias_k,
        color="#C44E52",
        linewidth=1.2,
        linestyle="--",
        label=f"bias = {_fmt(result.stats.bias_k)} K",
    )
    ax_hist.set_xlabel("derived - official (K)")
    ax_hist.set_ylabel("matchup count")
    ax_hist.set_title("difference histogram")
    ax_hist.legend(loc="upper right", fontsize=8)

    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def render_markdown_report(
    result: ValidationResult,
    plot_name: str,
    out_dir: str | Path,
) -> Path:
    """Render the Markdown validation report; return its path (REQ-VAL-04).

    Embeds the difference plot (``plot_name``, relative to the report) and tabulates
    the stats, per-threshold PASS/FAIL, the overall verdict, the thresholds used,
    and the run metadata (versions + timestamp). Labels SYNTHETIC inputs (SRD §5).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / _MD_NAME

    stats = result.stats
    thr = result.thresholds
    checks = result.checks

    lines: list[str] = []
    lines.append("# Validation report - derived SST vs official SL_2_WST")
    lines.append("")
    if result.synthetic_inputs:
        lines.append(
            "> **SYNTHETIC INPUTS.** This run used the offline SYNTHETIC fixtures, "
            "not real EUMETSAT data. The derived SST also uses a SIMPLIFIED "
            "split-window with nearest-neighbour co-location. These results are a "
            "demonstration of the validation mechanics and are **never** to be "
            "presented as operational."
        )
    else:
        lines.append(
            "> **Simplifications apply.** The derived SST uses a SIMPLIFIED "
            "split-window and nearest-neighbour co-location (see SRD §4). A "
            "simplification is never presented as operational."
        )
    lines.append("")
    lines.append(f"**Overall verdict: {_verdict(result.passed)}**")
    lines.append("")

    # --- Metadata ---
    lines.append("## Run metadata")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| Derived product | `{result.derived_product_id}` |")
    lines.append(f"| Reference product | `{result.reference_product_id}` |")
    lines.append(f"| Processor version | `{result.processor_version}` |")
    lines.append(f"| Config version | `{result.config_version}` |")
    lines.append(f"| Run timestamp (UTC) | {result.run_timestamp.isoformat()} |")
    lines.append(f"| Synthetic inputs | {'yes' if result.synthetic_inputs else 'no'} |")
    lines.append("")

    # --- Statistics ---
    lines.append("## Statistics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Matchup count | {stats.match_count} |")
    lines.append(f"| Bias (derived - official) | {_fmt(stats.bias_k)} K |")
    lines.append(f"| RMSE | {_fmt(stats.rmse_k)} K |")
    lines.append(f"| Std of differences | {_fmt(stats.std_k)} K |")
    lines.append(f"| Within +/-{_fmt(stats.tolerance_k)} K | {_fmt(stats.pct_within_tol)} % |")
    lines.append("")

    # --- Threshold gate ---
    lines.append("## Acceptance thresholds (REQ-VAL-03)")
    lines.append("")
    lines.append("| Check | Bound | Actual | Result |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| Matchup count | >= {thr.min_match_count} | {stats.match_count} | "
        f"{_verdict(checks.enough_matchups)} |"
    )
    lines.append(
        f"| \\|Bias\\| | <= {thr.max_abs_bias_k} K | {_fmt(stats.bias_k)} K | "
        f"{_verdict(checks.bias_within_bound)} |"
    )
    lines.append(
        f"| RMSE | <= {thr.max_rmse_k} K | {_fmt(stats.rmse_k)} K | "
        f"{_verdict(checks.rmse_within_bound)} |"
    )
    lines.append(
        f"| Within +/-{thr.tolerance_k} K | >= {thr.min_pct_within_tol} % | "
        f"{_fmt(stats.pct_within_tol)} % | {_verdict(checks.pct_within_tol_ok)} |"
    )
    lines.append("")
    lines.append(
        f"Reference quality filter: compared only where `quality_level >= {thr.min_quality_level}`."
    )
    lines.append("")

    # --- Plot ---
    lines.append("## Difference plot")
    lines.append("")
    lines.append(f"![derived - official SST difference]({plot_name})")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
