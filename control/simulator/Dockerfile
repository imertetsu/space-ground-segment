# SIMULATED spacecraft simulator image (FOS / Epic 2).
# Runtime is stdlib-only — no pip install, so the image build needs no network
# (avoids the Avast TLS interception that blocks pip/Maven in containers locally).
FROM python:3.11-slim

WORKDIR /app
COPY src ./src
COPY config ./config
ENV PYTHONPATH=/app/src

# Default: stream SIMULATED CCSDS/PUS telemetry to the Yamcs service over UDP.
# Override args via compose `command:` (host/port/rate/duration/seed/config).
ENTRYPOINT ["python", "-m", "sgs_sim.cli.main"]
CMD ["--host", "yamcs", "--port", "10015", "--duration", "0"]
