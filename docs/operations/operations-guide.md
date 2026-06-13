# Operations Guide (STUB)

> **STUB.** This guide is filled in as Epic 1 phases land. Sections marked _TBD_
> are placeholders. For exact, authoritative commands, defer to `CLAUDE.md`
> (quality gates / dev workflow) and the spec — this guide references them rather
> than duplicating them.

---

## Running Epic 1

### Phase 0 — environment setup & quality gates

- **Set up the Python environment** for `payload/` (virtualenv + editable install
  with dev extras): see `payload/README.md` (quickstart) and `CLAUDE.md §0` (the
  canonical gate table).
- **Run the quality gates** from `payload/`: `ruff check .`, `ruff format
  --check .`, `mypy src`, `pytest`, `lint-imports`; build via
  `docker compose build payload` from the repo root. Authoritative commands and
  baselines live in `CLAUDE.md §0`.
- **CI:** GitLab `.gitlab-ci.yml` is canonical (`lint → unit → integration →
  ivv-verification → build`); a GitHub Actions mirror (`.github/workflows/ci.yml`)
  runs the same gates on the GitHub remote.
- **Local Docker gotcha:** behind Avast (or any TLS-intercepting AV/proxy), the
  in-container `pip install` fails cert verification; supply the system CA bundle
  to the build or disable HTTPS scanning. CI runners are unaffected.

### Phase 1 — ingestion _(TBD — fill when the phase lands)_

- How to configure EUMETSAT Data Store credentials for `eumdac`. _(Currently
  **blocked** — credentials not yet available; offline/fixture flow only.)_
- How to discover and download L1 (`SL_1_RBT`) and official L2 (`SL_2_WST`).
- How ingested products are registered in the catalogue.

### Phase 2 — processing _(TBD)_

- How to run each processor independently (cloud mask, SST retrieval).
- Where outputs and their provenance/config-version stamps are written.

### Phase 3 — validation _(TBD)_

- How to run the co-located comparison vs the official L2.
- How to read the validation report and interpret pass/fail vs thresholds.

### Phase 4 — operations _(TBD)_

- **Reprocessing:** how to trigger on-demand reprocessing of a product.
- **Status:** how to query product/pipeline status via the operator CLI.
- **Anomalies / dead-letter:** how to inspect dead-lettered products and
  interpret anomaly signals.
- **3D view:** how to launch the read-only 3D view and read the
  illustrative-vs-data-driven labelling _(Epic 4)._

---

_Last updated: stub created during Epic 1 Phase 0. Expand per phase; do not let it
drift from the shipped CLI behaviour._
