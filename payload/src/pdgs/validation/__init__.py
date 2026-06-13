"""Validation of the derived L2 SST against the official L2 SST (REQ-VAL, Phase 3).

Modules:

* :mod:`pdgs.validation.colocation` — nearest-neighbour matchup (REQ-VAL-01).
* :mod:`pdgs.validation.stats` — bias / RMSE / std / % agreement (REQ-VAL-02).
* :mod:`pdgs.validation.result` — acceptance-threshold gate + JSON (REQ-VAL-02/03).
* :mod:`pdgs.validation.report` — Markdown report + difference plot (REQ-VAL-04).
* :mod:`pdgs.validation.orchestrate` — :func:`~pdgs.validation.orchestrate.validate_product`
  end-to-end; the pipeline fails (CLI returns non-zero) when results fall outside
  the configured thresholds (REQ-VAL-03), so CI gates on the validation outcome.

This is the ``validation`` layer: it may import ``processing``, ``ingestion``,
``catalogue`` and ``config``, but no lower layer imports it (import-linter enforced).
"""
