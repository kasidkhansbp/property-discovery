# Railway deployment

The ingestion layer deploys as **one independent, Dockerfile-built cron service**
(no always-on Dagster daemon, to minimise cost). It wakes on its monthly
schedule, runs the full job chain in one container, writes to the shared
Postgres, and exits. Its authoritative config is [`services/railway.json`](../../services/railway.json).

Every service is config-as-code: each has its own `railway.json`, so the build,
start command, health check, schedule, and restart policy are versioned in the
repo — you only set the root directory + config-file path (and the variables) in
the dashboard.

| Service | Root dir | Config file | Build / start | Schedule |
|---|---|---|---|---|
| **Postgres** | — | — | Railway DB plugin | always on |
| **Gateway** | `/` | `gateway/railway.json` | Nixpacks → `python -m uvicorn gateway.app.main:app --host 0.0.0.0 --port $PORT` | always on (can app-sleep) |
| **Frontend** | `/frontend` | `frontend/railway.json` | Nixpacks → `npm run build` → `npm run start` | always on (can app-sleep) |
| **ingestion** | `/` | `services/railway.json` | `services/Dockerfile` → `run_jobs.sh` (CMD) | 24th 06:00 UTC |

**Migrations run as a pre-deploy step, not in the job container.** The ingestion
service's `preDeployCommand` (`bash services/scripts/migrate.sh`) runs in a
one-off container *before* the jobs start, so the schema is current before any
load writes to it — and if it fails, Railway aborts the deploy instead of running
jobs against a stale schema. The Dockerfile has **no `ENTRYPOINT`** (only a
`CMD`) on purpose: Railway passes a service's start/pre-deploy command as
arguments to an exec-form `ENTRYPOINT`, which would silently turn the migrate
command into bogus job names and skip the migration.

The ingestion service runs these 10 jobs sequentially, in dependency order, on
the 24th of each month:

```
# ingest
epc_monthly_job
land_registry_ppd_monthly_job
os_open_uprn_load_job
# reconcile + mart
reconciliation_monthly_job
mart_coverage_metrics_job
# per-table quality snapshots
land_registry_sales_quality_job
epc_domestic_certificates_quality_job
os_open_uprn_quality_job
property_uprn_mapping_quality_job
key_duplication_quality_job
```

`run_jobs.sh` runs them under `set -e`, so a step never runs on top of a failed
upstream (the mart won't build if reconciliation failed). `restartPolicyType =
NEVER` leaves a finished/failed run stopped until the next monthly tick instead
of retry-looping and burning minutes.

> **Timing:** the 24th assumes the upstream sources have already published that
> month — EPC republishes early-month, and HMLR's monthly PPD delta lands around
> the 20th. On the 24th that's normally safe. If you ever need to decouple the
> ingest steps onto their own earlier schedules, split them into additional cron
> services (each the same Dockerfile image with its own start command + cron) —
> but run any given job in **exactly one** service so the downstream chain never
> fires twice.

Wiring (per service): New Service → same GitHub repo → Settings → set **Root
Directory** and **Railway Config File** from the table above (e.g. ingestion =
Root `/`, Config `services/railway.json`). Each json sets the build, start
command, health check, cron, and restart policy; you only add the variables
below. The gateway builds from repo root (`/`) because it imports `shared.db`
and installs the root `requirements.txt`; the frontend builds from `/frontend`.

## Variables

**Gateway**
- `POSTGRES_DSN=${{Postgres.DATABASE_URL}}`

**Frontend** (build-time — `VITE_API_BASE_URL` is baked into the bundle)
- `VITE_API_BASE_URL=https://<gateway-public-domain>`

**Ingestion service**
- `POSTGRES_DSN=${{Postgres.DATABASE_URL}}`   — serving DB the jobs write
- `DAGSTER_PG_URL=${{Postgres.DATABASE_URL}}` — Dagster run/event storage
  (services/dagster.yaml). Safe to share the serving database: Dagster keeps the
  default `alembic_version` table, while the serving schema uses a dedicated
  `serving_alembic_version` (see First-time setup §3), so they don't collide.
- `DAGSTER_HOME=/app/services` — holds dagster.yaml (run_jobs.sh also defaults to it)
- `R2_BUCKET`, `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`
- `EPC_API_TOKEN`
- `DUCKDB_MEMORY_LIMIT` / `DUCKDB_THREADS` — optional, default `5GB` / `4`, sized
  for the 8 GB service. Every DuckDB step is capped by these (see
  `services/jobs/ingestion/duckdb_support.py`); DuckDB otherwise sizes itself
  from the *host's* RAM and the container is OOM-killed with no traceback.
  Raise them together with the service's memory; lower the limit if Metrics
  still shows the run nearing the cap.
- `ALERT_WEBHOOK_URL` — **set this.** A Slack/Discord-compatible incoming webhook;
  `run_jobs.sh` posts which job died (and a success ping) to it. Without it, a
  failed monthly run is silent until you read the logs. Optional:
  `ALERT_ON_SUCCESS=0` to alert on failure only.

## First-time setup

1. Deploy Postgres and set the ingestion service's variables (below).
2. **Serving schema** — handled automatically: the ingestion service's
   `preDeployCommand` runs `migrate.sh` (`alembic upgrade head`) on every deploy,
   building every table from the models on a fresh DB.
   - **Exception — a DB the pipeline already populated** (tables exist, no
     `alembic_version` row yet): a plain `upgrade head` would try to re-create
     existing tables and fail. Baseline it **once** before the first deploy, with
     the Railway CLI linked to the environment:
     `railway run --service ingestion bash services/scripts/migrate.sh stamp 0001`.
     Later deploys then run `upgrade head` cleanly.
3. **Dagster run/event storage** — Dagster keeps its run/event/schedule tables in
   Postgres (`DAGSTER_PG_URL`) and version-controls them with Alembic, using
   Alembic's default version table `alembic_version` (hard-coded, no rename). The
   serving schema uses Alembic too, so to share one database without the two
   fighting over that one table — which crashes every job with
   `ResolutionError: No such revision or branch '0001'` — the **serving** migrations
   record their revisions in a dedicated table, `serving_alembic_version`
   (`shared/migrations/env.py`), leaving plain `alembic_version` to Dagster.

   - **Fresh database:** nothing to do — the serving `migrate.sh` writes
     `serving_alembic_version`, Dagster creates its own `alembic_version`, done.
   - **If you deployed before this split** (the serving `migrate.sh` had already
     written `0001` into the shared `alembic_version`), remove that stray row
     **once** so Dagster can own the table, then redeploy:
     ```sql
     DROP TABLE IF EXISTS alembic_version;   -- against the shared DB
     ```
     On the next deploy the serving `migrate.sh` rebuilds its state in
     `serving_alembic_version` (idempotent — `create_all` skips the tables that
     already exist), and Dagster recreates and stamps its own `alembic_version`.
   - Optionally, one-off to keep Dagster's tables version-current:
     `railway run --service ingestion dagster instance migrate`
     (`DAGSTER_HOME=/app/services` is baked into the image).
4. Deploy Gateway, copy its public domain.
5. Set the Frontend's `VITE_API_BASE_URL` to that domain, then deploy Frontend.
6. Deploy the ingestion service (its pre-deploy migrate runs, then the jobs).

## Seeding the tables (one-off backfills)

The backfill / full-rebuild jobs have **no schedule** and aren't wired to the
cron service. Run them once, in dependency order, to populate the DB before the
monthly deltas make sense:

```
land_registry_ppd_backfill_job     # ~5 GB complete file
epc_backfill_job
os_open_uprn_load_job
reconciliation_full_job            # after land_registry + epc are loaded
```

Run each with the same dispatcher, against the Railway environment, e.g.:

```bash
# from a checkout, with Railway CLI linked to the project/environment:
railway run --service ingestion bash services/scripts/run_jobs.sh land_registry_ppd_backfill_job
```

Backfills are large: give the service more memory/disk temporarily (Railway
service → Settings → Resources), since the full files are far bigger than the
monthly deltas. The ephemeral container disk must hold the downloaded file +
cleaned parquet during the run.

## Inspecting runs

There's no always-on Dagster UI in this layout, but run history/logs persist in
Postgres. To look at them, start the webserver ad hoc against the same env:

```bash
railway run bash services/scripts/start_dagster.sh   # then open the forwarded port
```

`services/scripts/start_dagster.sh` is kept only for this (and for the alternative
always-on layout); it is not a deployed service here.
