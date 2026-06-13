# PDGS — Payload Data Ground Segment (Epic 1)

Ingests real **Sentinel-3 SLSTR Level-1B** data, runs a chained processor
(cloud screening → simplified split-window SST), and validates the result against
the **official SLSTR Level-2 SST** product.

**Phase 0 status:** skeleton + quality gates only — no processing logic yet.
See `../docs` (SRD/ICD/SVP) and `../CLAUDE.md` for conventions and gate commands.

## Quality gates (run from this `payload/` directory)

```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows; use bin/ on POSIX
pip install -e ".[dev]"
ruff check .
ruff format --check .
mypy src
pytest
lint-imports
```

## Layout

```
src/pdgs/
├── cli/         operator CLI surface (REQ-OPS)
├── validation/  derived-L2 vs official-L2 comparison + report (REQ-VAL)
├── processing/  cloud_screening/ + sst_retrieval/ (REQ-PRO)
├── ingestion/   eumdac discover/download/integrity + catalogue register (REQ-ING)
├── catalogue/   product/provenance catalogue access (REQ-ING-04)
└── config/      versioned params, coefficients, thresholds (REQ-CFG)
```

Dependency direction (enforced by `import-linter`): `cli → operations → validation
→ processing → ingestion → catalogue → config`.

## CLI (operator)

Offline demo uses the synthetic fixtures + `config/fixture.toml`:

```bash
pdgs run --config config/fixture.toml   # ingest -> process -> validate (end-to-end)
pdgs ingest                             # discover/download/verify/register fixtures
pdgs process  --config config/fixture.toml
pdgs validate --config config/fixture.toml
pdgs status [--status STATUS] [--type TYPE]   # list catalogue (shows config_version)
pdgs reprocess <product_id> [--validate]      # on-demand re-run
pdgs dead-letter                              # list FAILED products
```

See `../docs/operations/operations-guide.md` for details and the real-data path.
