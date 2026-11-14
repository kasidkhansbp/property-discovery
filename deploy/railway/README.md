# Railway deployment

The ingestion layer deploys as **one independent, Dockerfile-built cron service**
(no always-on Dagster daemon, to minimise cost). It wakes on its monthly
schedule, runs the full job chain in one container, writes to the shared
Postgres, and exits. Its authoritative config is [`services/railway.json`](../../services/railway.json).

| Service | Source | Start command | Schedule |
|---|---|---|---|
| **Postgres** | Railway DB plugin | — | always on |
| **Gateway** | repo `/` | `uvicorn gateway.app.main:app --host 0.0.0.0 --port $PORT` | always on (can app-sleep) |
| **Frontend** | repo `/frontend` | `npm run start` | always on (can app-sleep) |
| **ingestion** | repo `/` + `services/Dockerfile` (via `services/railway.json`) | (from railway.json) | 24th 06:00 UTC |

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

Wiring: New Service → same GitHub repo → Settings → **Railway Config File** =
`services/railway.json` → Root Directory `/`. The json sets the build (Dockerfile),
start command, cron, and restart policy; you only add the variables below.

## Variables

**Gateway**
- `POSTGRES_DSN=${{Postgres.DATABASE_URL}}`

**Frontend** (build-time — `VITE_API_BASE_URL` is baked into the bundle)
- `VITE_API_BASE_URL=https://<gateway-public-domain>`

**Ingestion service**
- `POSTGRES_DSN=${{Postgres.DATABASE_URL}}`   — serving DB the jobs write
- `DAGSTER_PG_URL=${{Postgres.DATABASE_URL}}` — Dagster run/event storage (services/dagster.yaml)
- `DAGSTER_HOME=/app/services` — holds dagster.yaml (run_jobs.sh also defaults to it)
- `R2_BUCKET`, `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`
- `EPC_API_TOKEN`
- `ALERT_WEBHOOK_URL` — **set this.** A Slack/Discord-compatible incoming webhook;
  `run_jobs.sh` posts which job died (and a success ping) to it. Without it, a
  failed monthly run is silent until you read the logs. Optional:
  `ALERT_ON_SUCCESS=0` to alert on failure only.

## First-time setup

1. Deploy Postgres, then run **two** one-off migrations (from the ingestion
   service shell or locally with the same env):
   - Dagster run/event storage: `DAGSTER_HOME=/app/services dagster instance migrate`
   - Serving schema (shared/migrations, via Alembic): `bash services/scripts/migrate.sh`
     On a database the pipeline already populated, baseline it first instead:
     `bash services/scripts/migrate.sh stamp 0001`, then `upgrade head` on later
     deploys. On a fresh DB, `upgrade head` builds every table from the models.
     (The service's start command also runs `migrate.sh` before the jobs.)
2. Deploy Gateway, copy its public domain.
3. Set the Frontend's `VITE_API_BASE_URL` to that domain, then deploy Frontend.
4. Deploy the ingestion service.

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
