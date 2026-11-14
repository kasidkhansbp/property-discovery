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
#
# Failure alerting: set ALERT_WEBHOOK_URL to a Slack/Discord-compatible incoming
# webhook and this script posts which job died (and, optionally, a success ping).
# Without it, a failed monthly run is silent until you check the logs — so set it.
#   ALERT_WEBHOOK_URL   Slack/Discord-style incoming webhook (unset = log only)
#   ALERT_ON_SUCCESS    "1" (default) also pings when the whole chain succeeds;
#                       set to "0" for failures-only.
set -euo pipefail

# Resolve locations from this script's own path, so it works no matter the
# caller's cwd (container ENTRYPOINT, Railway startCommand, or a local shell).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # services/scripts
SERVICES_DIR="$(dirname "${SCRIPT_DIR}")"                   # services
REPO_ROOT="$(dirname "${SERVICES_DIR}")"                    # parent of services/

# Postgres-backed instance (schedule/run/event storage) lives in
# services/dagster.yaml — same config the UI uses.
export DAGSTER_HOME="${DAGSTER_HOME:-${SERVICES_DIR}}"

ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}"
ALERT_ON_SUCCESS="${ALERT_ON_SUCCESS:-1}"
# Railway injects these; used only to label the alert so you know which
# service/environment it came from. Harmless when unset (e.g. local runs).
SERVICE_LABEL="${RAILWAY_SERVICE_NAME:-ingestion}"
ENV_LABEL="${RAILWAY_ENVIRONMENT_NAME:-}"

# Post a plain-text message to ALERT_WEBHOOK_URL as a Slack/Discord-style
# {"text": ...} payload. Best-effort: a webhook outage must NOT change the run's
# exit code, so every failure path here is swallowed. No-op if the URL is unset.
_post_webhook() {
  [[ -z "${ALERT_WEBHOOK_URL}" ]] && return 0
  local msg="$1"
  if command -v python3 >/dev/null 2>&1; then
    ALERT_MSG="${msg}" ALERT_URL="${ALERT_WEBHOOK_URL}" python3 - <<'PY' \
      || echo "run_jobs.sh: alert webhook POST failed (ignored)" >&2
import json, os, urllib.request
data = json.dumps({"text": os.environ["ALERT_MSG"]}).encode("utf-8")
req = urllib.request.Request(
    os.environ["ALERT_URL"], data=data,
    # Discord 403s the default "Python-urllib" User-Agent; a custom one is
    # required. (Slack tolerates either.) Keep it generic — no user info.
    headers={"Content-Type": "application/json", "User-Agent": "ingestion-alert/1.0"},
)
urllib.request.urlopen(req, timeout=15).read()
PY
  elif command -v curl >/dev/null 2>&1; then
    # Minimal JSON escaping for the curl fallback (message is controlled text:
    # job names + service labels), enough to stay valid JSON.
    local esc=${msg//\\/\\\\}; esc=${esc//\"/\\\"}
    curl -sS -m 15 -X POST -H 'Content-Type: application/json' \
      -A 'ingestion-alert/1.0' \
      --data-binary "{\"text\":\"${esc}\"}" "${ALERT_WEBHOOK_URL}" >/dev/null \
      || echo "run_jobs.sh: alert webhook POST failed (ignored)" >&2
  else
    echo "run_jobs.sh: ALERT_WEBHOOK_URL set but no python3/curl to send it" >&2
  fi
}

# Log a line AND mirror it to the webhook.
notify() {
  echo "$1"
  _post_webhook "$1"
}

# Run from the repo root so the `services.jobs.ingestion.*` imports resolve.
cd "${REPO_ROOT}"

if [[ "$#" -eq 0 ]]; then
  echo "run_jobs.sh: no job names given" >&2
  exit 2
fi

where="${SERVICE_LABEL}${ENV_LABEL:+/${ENV_LABEL}}"

for job in "$@"; do
  echo ">>> dagster job execute -j ${job}"
  # `|| rc=$?` keeps `set -e` from exiting before we can alert, while capturing
  # the job's REAL exit code (an `if ! cmd` would mask it as 0). We re-exit with
  # that same code right after notifying, so the container still fails the run.
  rc=0
  # Target the code location by MODULE (services/definitions.py's `defs`), not a
  # workspace file: `dagster job execute` has no -w/--workspace option (that's a
  # `dagster dev`/webserver flag) and errors "No such option '-w'". We cd'd to
  # REPO_ROOT above, so `services.definitions` imports cleanly.
  dagster job execute -j "${job}" -m services.definitions || rc=$?
  if [[ "${rc}" -ne 0 ]]; then
    notify ":red_circle: ingestion run FAILED at job \`${job}\` (exit ${rc}) on ${where}. Remaining jobs were SKIPPED. Inspect the Dagster run history in Postgres."
    exit "${rc}"
  fi
  echo "<<< ${job} finished"
done

echo "All jobs completed: $*"
if [[ "${ALERT_ON_SUCCESS}" == "1" ]]; then
  notify ":white_check_mark: ingestion run completed on ${where}: $*"
fi
