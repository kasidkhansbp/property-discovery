#!/usr/bin/env bash
# One-shot Dagster job runner for Railway CRON services.
#
# Replaces the always-on Dagster daemon: instead of a 24/7 process firing
# monthly schedules, each Railway cron service boots this script, runs the job(s)
# it was given IN ORDER, and exits. Railway then tears the container down until
# the next cron tick, so you pay only for the minutes a run actually uses.
#
# Usage (as a Railway start command):
#   bash scripts/run_jobs.sh <job_name> [<job_name> ...]
#
# Jobs run sequentially and `set -e` stops at the first failure, so a dependent
# job never runs on top of a failed upstream (e.g. the mart won't build if the
# reconciliation job failed). Run history/logs land in Postgres (dagster.yaml),
# so a failed monthly run is still inspectable after the container is gone.
set -euo pipefail

# Resolve locations from this script's own path, so it works no matter the
# caller's cwd (container ENTRYPOINT, Railway startCommand, or a local shell).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # services/scripts
SERVICES_DIR="$(dirname "${SCRIPT_DIR}")"                   # services
REPO_ROOT="$(dirname "${SERVICES_DIR}")"                    # parent of services/

# Postgres-backed instance (schedule/run/event storage) lives in
# services/dagster.yaml — same config the UI uses.
export DAGSTER_HOME="${DAGSTER_HOME:-${SERVICES_DIR}}"

# Run from the repo root so the `services.jobs.ingestion.*` imports resolve.
cd "${REPO_ROOT}"

if [[ "$#" -eq 0 ]]; then
  echo "run_jobs.sh: no job names given" >&2
  exit 2
fi

for job in "$@"; do
  echo ">>> dagster job execute -j ${job}"
  dagster job execute -j "${job}" -w services/workspace.yaml
  echo "<<< ${job} finished"
done

echo "All jobs completed: $*"
