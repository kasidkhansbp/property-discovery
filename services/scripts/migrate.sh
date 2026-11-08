#!/usr/bin/env bash
# Apply the serving-database schema migrations (shared/migrations) with Alembic.
#
# Run this before the jobs on a deploy, so the served tables exist / are current
# before a load writes to them:
#   bash services/scripts/migrate.sh                 # upgrade to head
#   bash services/scripts/migrate.sh stamp 0001      # baseline an existing DB
#
# On a database the ingestion pipeline already populated (tables exist, no
# alembic_version yet), baseline it once with `stamp 0001`, then future deploys
# run plain `upgrade head`. On a fresh database, `upgrade head` builds everything.
#
# Needs POSTGRES_DSN set (the same serving DB the jobs write).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # services/scripts
SERVICES_DIR="$(dirname "${SCRIPT_DIR}")"                   # services
REPO_ROOT="$(dirname "${SERVICES_DIR}")"                    # parent of services/

cd "${REPO_ROOT}"

# Default action is `upgrade head`; any args are passed straight to alembic.
if [[ "$#" -eq 0 ]]; then
  set -- upgrade head
fi

echo ">>> alembic -c shared/alembic.ini $*"
exec python -m alembic -c shared/alembic.ini "$@"
