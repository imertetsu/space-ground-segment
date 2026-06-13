# sgs-sim — SIMULATED spacecraft simulator (FOS / Epic 2)

Emits **CCSDS Space Packets** carrying **PUS** telemetry over UDP into Yamcs:
periodic PUS-3 housekeeping, PUS-5 events, and PUS-1 command verification (Phase 3).

> **SIMULATED.** The telemetry is synthetic but CCSDS/PUS-compliant in structure,
> and is labelled simulated everywhere. It is **not** operational spacecraft data.

## Run

```bash
cd control/simulator
python -m venv .venv && source .venv/Scripts/activate   # Windows; bin/ on POSIX
pip install -e ".[dev]"
sgs-sim                  # stream HK to 127.0.0.1:10015 (Yamcs UdpTmDataLink)
```

## Gates (from this directory)

```bash
ruff check . && ruff format --check . && mypy src && pytest
```

See `docs/specs/control.md`, `docs/icd` §2 (packet/APID field-map) and
`docs/srd` §1A for the requirements and the frozen decode contract.
