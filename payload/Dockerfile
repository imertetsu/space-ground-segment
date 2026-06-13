# PDGS payload service — Phase 0 skeleton image.
# Build context is ./payload (see docker-compose.yml at the repo root).
FROM python:3.11-slim AS base

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

# Phase 0 has no long-running process: the operator CLI prints status and exits.
ENTRYPOINT ["pdgs"]
CMD ["status"]
