# control/ — FOS (Flight Operations Segment)

Epic 2. Spacecraft **simulator** (CCSDS/PUS) → **Yamcs** (XTCE mission database) →
decommutation, limit-checking, telecommanding. **Telemetry is SIMULATED** and is
labelled as such (see `docs/srd` §5). Not operational software.

- `yamcs/` — the Yamcs MCS, based on the official Yamcs **quickstart**. Build/run
  via the bundled Maven Wrapper (`mvnw`); no global Maven needed.
- `simulator/` — our Python CCSDS/PUS simulator (Phase 1+). _Phase 0 uses the
  quickstart's own `yamcs/simulator.py` to prove the toolchain + ingest loop._

## Run (Phase 0 — native; proves the loop)

```bash
cd control/yamcs
./mvnw yamcs:run          # Yamcs; web UI at http://localhost:8090 (instance "myproject")
python simulator.py       # feeds CCSDS packets over UDP :10015 (TM); TC on :10025
```
Then open <http://localhost:8090> → Telemetry → Parameters (live decommutated values).

## Behind a TLS-intercepting AV (Avast) on this machine

Maven/curl/Java HTTPS fail cert verification unless configured (CI runners are
unaffected — this is local only):

```bash
export JDK_JAVA_OPTIONS="-Djavax.net.ssl.trustStoreType=Windows-ROOT"   # Java/Maven dep downloads
export CURL_HOME=<dir with a .curlrc containing: ssl-no-revoke>          # mvnw's curl (Schannel revocation)
```
(git clone/push for this repo use `http.sslBackend=schannel`.)

> **Phase 0 scope:** prove that Yamcs builds + runs on this machine (behind Avast)
> and decommutates a CCSDS packet via an XTCE MDB — done with the stock quickstart.
> Our mission HK parameters, the **labelled** simulator, raw→eng calibration,
> limits, and the command set arrive in Phases 1–3 (see `docs/specs/control.md`,
> `docs/srd`, `docs/icd`).
