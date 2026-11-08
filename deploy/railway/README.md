# Railway deployment

Six services in one Railway project. The ingestion layer runs as **cron
services** (no always-on Dagster daemon) to minimise cost — each wakes on its
schedule, runs its job(s), and exits.

| Service | Source | Start command | Schedule |
|---|---|---|---|
| **Postgres** | Railway DB plugin | — | always on |
| **Gateway** | repo `/` | `uvicorn gateway.app.main:app --host 0.0.0.0 --port $PORT` | always on (can app-sleep) |
| **Frontend** | repo `/frontend` | `npm run start` | always on (can app-sleep) |
| **cron-epc** | repo `/` + `deploy/railway/cron-epc.toml` | (from toml) | 5th 04:00 UTC |
| **cron-land-registry** | repo `/` + `deploy/railway/cron-land-registry.toml` | (from toml) | 23rd 03:00 UTC |
| **cron-monthly-24th** | repo `/` + `deploy/railway/cron-monthly-24th.toml` | (from toml) | 24th 06:00 UTC |

Each cron service: New Service → same GitHub repo → Settings → **Railway Config
File** = the matching `deploy/railway/*.toml` → Root Directory `/`. The toml sets
the start command, cron, and restart policy; you only add the variables below.

## Variables

**Gateway**
- `POSTGRES_DSN=${{Postgres.DATABASE_URL}}`

**Frontend** (build-time — `VITE_API_BASE_URL` is baked into the bundle)
- `VITE_API_BASE_URL=https://<gateway-public-domain>`

**All three cron services** (identical set)
- `POSTGRES_DSN=${{Postgres.DATABASE_URL}}`   — serving DB the jobs write
- `DAGSTER_PG_URL=${{Postgres.DATABASE_URL}}` — Dagster run/event storage (services/dagster.yaml)
- `DAGSTER_HOME=/app/services` — holds dagster.yaml (run_jobs.sh also defaults to it)
- `R2_BUCKET`, `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`
- `EPC_API_TOKEN`

> Tip: put the shared cron variables in a Railway **shared variable group** and
> reference them from all three services so they stay in sync.

## First-time setup

1. Deploy Postgres, then run **two** one-off migrations (from a cron service
   shell or locally with the same env):
   - Dagster run/event storage: `DAGSTER_HOME=/app/services dagster instance migrate`
   - Serving schema (shared/migrations, via Alembic): `bash services/scripts/migrate.sh`
     On a database the pipeline already populated, baseline it first instead:
     `bash services/scripts/migrate.sh stamp 0001`, then `upgrade head` on later
     deploys. On a fresh DB, `upgrade head` builds every table from the models.
2. Deploy Gateway, copy its public domain.
3. Set the Frontend's `VITE_API_BASE_URL` to that domain, then deploy Frontend.
4. Deploy the three cron services.

## Seeding the tables (one-off backfills)

The backfill / full-rebuild jobs have **no schedule** and aren't wired to any
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
railway run --service cron-land-registry bash services/scripts/run_jobs.sh land_registry_ppd_backfill_job
```

Backfills are large: give whichever service runs them more memory/disk
temporarily (Railway service → Settings → Resources), since the full files are
far bigger than the monthly deltas. The ephemeral container disk must hold the
downloaded file + cleaned parquet during the run.

## Inspecting runs

There's no always-on Dagster UI in this layout, but run history/logs persist in
Postgres. To look at them, start the webserver ad hoc against the same env:

```bash
railway run bash services/scripts/start_dagster.sh   # then open the forwarded port
```

`services/scripts/start_dagster.sh` is kept only for this (and for the alternative
always-on layout); it is not a deployed service here.

## Optional: OS Open UPRN auto-refresh

`os_open_uprn_load_job` has no schedule upstream (OS republishes ~every 6 weeks;
the download step no-ops via md5 when nothing changed). If you want it unattended,
add a 4th cron service with `startCommand = "bash services/scripts/run_jobs.sh os_open_uprn_load_job"`
and a weekly `cronSchedule` (e.g. `0 2 * * 1`).
