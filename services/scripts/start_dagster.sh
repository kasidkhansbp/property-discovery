#!/usr/bin/env bash
# Start command for the Railway "service layer" service.
#
# Dagster needs TWO long-running processes: the daemon (fires schedules / runs
# the queue) and the webserver (UI + GraphQL). Railway runs one start command
# per service, so we launch the daemon in the background and exec the webserver
# in the foreground as the container's main process. If the webserver exits,
# the container exits and Railway restarts it.
#
# DAGSTER_HOME must be a dir that contains dagster.yaml; it defaults to the
# services/ dir (resolved from this script's path below), which holds it.
set -euo pipefail

# Resolve locations from this script's own path (see run_jobs.sh).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # services/scripts
SERVICES_DIR="$(dirname "${SCRIPT_DIR}")"                   # services
REPO_ROOT="$(dirname "${SERVICES_DIR}")"                    # parent of services/

# DAGSTER_HOME must be a dir containing dagster.yaml — services/ holds it.
export DAGSTER_HOME="${DAGSTER_HOME:-${SERVICES_DIR}}"

# Force Dagster's Postgres storage onto psycopg2 (see run_jobs.sh for the full
# rationale): SQLAlchemy 2.1 defaults `postgresql://` to psycopg (v3), which can't
# bind a parameter in `NOTIFY run_events, <payload>` and crashes every run with
# "syntax error at or near $1". psycopg2 inlines the literal. dagster-io/dagster#34232.
if [[ -n "${DAGSTER_PG_URL:-}" ]]; then
  case "${DAGSTER_PG_URL}" in
    postgresql://*) export DAGSTER_PG_URL="postgresql+psycopg2://${DAGSTER_PG_URL#postgresql://}" ;;
    postgres://*)   export DAGSTER_PG_URL="postgresql+psycopg2://${DAGSTER_PG_URL#postgres://}" ;;
  esac
fi

# Run from the repo root so the `services.jobs.ingestion.*` imports resolve.
cd "${REPO_ROOT}"

# Fire the daemon in the background; it reads the same DAGSTER_HOME/dagster.yaml.
dagster-daemon run &

# Foreground: the webserver binds the port Railway expects.
exec dagster-webserver -h 0.0.0.0 -p "${PORT:-3000}" -w services/workspace.yaml
