// Railway Infrastructure as Code (IaC) — replaces the per-service railway.json
// files, which Railway stops reading on 2026-12-01 (Config as Code is deprecated).
//
// This one project-level file defines all three app services. The Postgres
// database is a Railway plugin and is intentionally NOT declared here, so IaC
// leaves it untouched; the services reference it by name via `${{Postgres.*}}`.
//
// Authoritative schema: the `railway` npm SDK types (v3.17.0). Note that the
// Dockerfile builder, cronSchedule, restartPolicy* and preDeployCommand are
// fully supported by the SDK even though Railway's prose docs don't show them.
//
// Workflow (run from the repo root, with the Railway CLI linked to the env):
//   npm install                 # installs the `railway` SDK (root package.json)
//   railway login && railway link
//   railway config plan         # preview — VERIFY builder/cron/restart/preDeploy
//   railway config apply        # apply once the plan looks right
// Then delete the three railway.json files and clear each service's
// "Railway Config File" field so nothing is managed by both systems.

import { defineRailway, project, github, service, preserve } from "railway/iac";

// GitHub repo that every service builds from (owner/repo).
const REPO = "kasidkhansbp/property-discovery";

export default defineRailway(() => {
  // Gateway — FastAPI, Nixpacks, built from the repo root (imports shared.db
  // and the root requirements.txt). Always on; can app-sleep.
  const gateway = service("Gateway", {
    source: github(REPO),
    build: { builder: "NIXPACKS" },
    start: "uvicorn gateway.app.main:app --host 0.0.0.0 --port $PORT",
    healthcheck: "/health",
    deploy: {
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 10,
    },
    env: {
      POSTGRES_DSN: "${{Postgres.DATABASE_URL}}",
    },
  });

  // Frontend — Vite SPA, Nixpacks, built from /frontend. VITE_API_BASE_URL is
  // baked into the bundle at BUILD time, so it must point at the gateway's
  // public domain (service must be named "Gateway" for this reference).
  const frontend = service("Frontend", {
    source: github(REPO, { rootDirectory: "frontend" }),
    build: { builder: "NIXPACKS" },
    start: "npm run start",
    deploy: {
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 10,
    },
    env: {
      VITE_API_BASE_URL: "https://${{Gateway.RAILWAY_PUBLIC_DOMAIN}}",
    },
  });

  // Ingestion — Dockerfile-built one-shot cron job (24th, 06:00 UTC). No start
  // command: the image's CMD runs the full monthly job chain and exits.
  // preDeploy runs the Alembic migration in a one-off container first.
  // restartPolicyType NEVER leaves a finished/failed run stopped until the
  // next monthly tick instead of retry-looping.
  const ingestion = service("ingestion", {
    source: github(REPO),
    build: {
      builder: "DOCKERFILE",
      dockerfilePath: "services/Dockerfile",
    },
    preDeploy: "bash services/scripts/migrate.sh",
    deploy: {
      cronSchedule: "0 6 24 * *",
      restartPolicyType: "NEVER",
      numReplicas: 1,
    },
    env: {
      // Non-secret config — codified here so it shows up in `plan`.
      POSTGRES_DSN: "${{Postgres.DATABASE_URL}}",
      DAGSTER_PG_URL: "${{Postgres.DATABASE_URL}}",
      DAGSTER_HOME: "/app/services",
      // Secrets — keep whatever is already set in the dashboard; never commit
      // their values. Set them once in the Railway dashboard, then preserve().
      R2_BUCKET: preserve(),
      R2_ENDPOINT_URL: preserve(),
      R2_ACCESS_KEY_ID: preserve(),
      R2_SECRET_ACCESS_KEY: preserve(),
      EPC_API_TOKEN: preserve(),
      ALERT_WEBHOOK_URL: preserve(),
    },
  });

  // Project name must match your Railway project's name (adopts it instead of
  // trying to rename). Postgres is a plugin and is left out on purpose.
  return project("delightful-friendship", {
    resources: [gateway, frontend, ingestion],
  });
});
