# syntax=docker/dockerfile:1
#
# Ingestion service image — the Dagster pipelines under services/jobs/ingestion,
# packaged so the "service layer" deploys and runs independently of the
# gateway/frontend. The service's own files (definitions.py, workspace.yaml,
# dagster.yaml, scripts/, requirements.txt) live under services/; the DB schema
# models + Alembic migrations it imports live under shared/ (both copied below).
# Run migrations with services/scripts/migrate.sh before the jobs — the Railway
# preDeployCommand in services/railway.json (and the deploy README) does this.
#
# It runs as a ONE-SHOT job: the container boots, runs the pipeline chain via
# services/scripts/run_jobs.sh, writes to the shared Postgres, and exits. A
# scheduler (railway.json cron / K8s CronJob / cloud job runner) fires it monthly.
#
# BUILD CONTEXT MUST BE THE REPO ROOT — the Python package is named `services`,
# so its parent (the repo root) has to be on sys.path for imports to resolve:
#   docker build -f services/Dockerfile -t property-ingestion .

FROM python:3.12-slim AS base

# - PYTHONUNBUFFERED: stream logs straight to the orchestrator (no stuck buffer)
# - PYTHONDONTWRITEBYTECODE: no stray .pyc in the image
# - DAGSTER_HOME: dir that holds dagster.yaml — now services/ (i.e. /app/services)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DAGSTER_HOME=/app/services

WORKDIR /app

# System deps: bash runs the run_jobs.sh entrypoint; ca-certificates for HTTPS to
# R2 and the source downloads. psycopg[binary], duckdb and boto3 ship manylinux
# wheels, so there's no need for a build toolchain or libpq-dev.
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps in their own layer so editing code doesn't re-run pip.
COPY services/requirements.txt ./services/requirements.txt
RUN pip install -r services/requirements.txt

# App code: the services/ package (jobs, definitions.py, workspace.yaml,
# dagster.yaml, scripts/) and the shared/ DB library it imports (models,
# connection, Alembic migrations). Both sit under /app so the `services.*` and
# `shared.*` imports resolve with /app on sys.path. Nothing from gateway/,
# frontend/ or tests/.
COPY services/ ./services/
COPY shared/ ./shared/

# Drop root for the run.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Default command: run the full monthly chain in dependency order, then exit.
# run_jobs.sh resolves its own paths and runs the jobs sequentially under
# `set -e`, so a step never runs on a failed upstream. The *schedule* and the
# pre-deploy schema migration live in the platform (services/railway.json), not
# here.
#
# This is a plain CMD with NO ENTRYPOINT, on purpose. Railway passes a service's
# Start Command / Pre-Deploy Command as *arguments* to any exec-form ENTRYPOINT,
# which would turn "bash migrate.sh ..." into bogus Dagster job names and skip
# the migration entirely. Keeping the whole launcher in CMD lets railway.json's
# preDeployCommand run migrations cleanly, while this CMD remains the default
# "run the jobs" command (override it to run a one-off job, e.g. a backfill).
CMD ["bash", "services/scripts/run_jobs.sh", \
     "epc_monthly_job", \
     "land_registry_ppd_monthly_job", \
     "os_open_uprn_load_job", \
     "reconciliation_monthly_job", \
     "mart_coverage_metrics_job", \
     "land_registry_sales_quality_job", \
     "epc_domestic_certificates_quality_job", \
     "os_open_uprn_quality_job", \
     "property_uprn_mapping_quality_job", \
     "key_duplication_quality_job"]
