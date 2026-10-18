# reconciliation

Maps HM Land Registry transactions (`transaction_id`) to EPC **UPRNs**, producing
the `property_uprn_mapping` bridge table. Self-contained Dagster service: owns its
own assets, jobs + monthly schedule. Unlike land_registry and epc it downloads
nothing — it reads the two core tables those services already loaded
(`land_registry_sales`, `epc_domestic_certificates`) and reconciles them.

Two chains, both `normalize keys → exact + fuzzy match → load to Postgres`:

| Chain | Trigger | Purpose |
|-------|---------|---------|
| **full** | **manual** (`reconciliation_full_job`) | one-off rebuild of the whole bridge after the LR/EPC backfills |
| **incremental** | **scheduled** (`reconciliation_monthly_job`, `0 6 24 * *`) | reconcile new transactions after the monthly LR delta; **protects** already-decided `transaction_id`s |

Matching: keys are normalized to one `addr_key` per side (LR PAON + Street, EPC
address1) plus a whitespace-stripped `norm_postcode`. **EXACT** = equal
`(norm_postcode, addr_key)` → score 1.0. **FUZZY** = best DuckDB
`jaro_winkler_similarity` over candidates sharing a postcode, kept above the
threshold. Then full coverage: every transaction and every UPRN appears, with
`UNMATCHED_LR` / `UNMATCHED_UPRN` rows for the leftovers. One best UPRN per
`transaction_id` (1:1); a UPRN may recur across many transactions (1:many).

## Files
| File | Role |
|------|------|
| `assets.py`     | Both chains, built from one asset factory (`_build_reconciliation_assets`) |
| `utils.py`      | Shared normalize / build-master / load step logic |
| `schema.py`     | Single source of truth for the `property_uprn_mapping` columns + match tiers |
| `schedules.py`  | Full job (manual), monthly job + schedule |
| `resources.py`  | Reuses land_registry's R2 + Postgres connections |
| `__init__.py`   | Bundles this service's own `Definitions` (resources from env vars) |

Nothing touches the local filesystem: DuckDB reads the source tables over its
postgres extension, reads/writes Parquet in R2 over httpfs, and loads Postgres via
the postgres extension. Match scoring stays in-engine (native Jaro-Winkler).

## Credentials (from the environment — never the repo)
```
R2_BUCKET, R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, POSTGRES_DSN
```

## Run it (from the repo root)
```bash
dagster job execute -f definitions.py -j reconciliation_full_job
# or watch it in the UI:
dagster dev            # then launch reconciliation_full_job
```
Run the **full** job once after the land_registry and epc backfills have populated
their tables; then let the monthly schedule maintain the bridge.

## TODO: faster, readable, trackable full load (load-and-swap)

The full path in `load_master` (`utils.py`) does `TRUNCATE target; INSERT INTO
target SELECT * FROM staging` in **one transaction**. At backfill scale (~40.6M
master rows) this has three problems:

- **Slow** — it writes the 40M rows **twice** (once into staging, then a second
  full copy into the target), and builds the target's indexes row-by-row during
  the INSERT.
- **Blocks all reads** — `TRUNCATE` holds `ACCESS EXCLUSIVE` on
  `property_uprn_mapping` for the whole ~20+ min transaction, so nothing else can
  even read the table (not `count(*)`, not `pg_relation_size`) until it commits.
- **No progress** — Postgres has no progress view for `INSERT`/DML, and the
  exclusive lock hides the in-progress rows from every other session anyway.

Fix the **full** path (only — the incremental path's `ON CONFLICT DO NOTHING` +
unmatched-UPRN refresh must stay, or it would discard protected matches):

- **Load-and-swap** → bulk-load the master Parquet **once** into a fresh side
  table, `CREATE INDEX` on it in bulk (faster than per-row index maintenance),
  then swap it in with a millisecond `ALTER TABLE ... RENAME` inside a short
  transaction. The live table stays readable throughout; the exclusive lock is
  held only for the rename.
- **Trackable** → because the side table isn't locked, `count(*)` on it climbs as
  it fills — real progress. (Loading it via `COPY` additionally unlocks
  `pg_stat_progress_copy` for tuple-level progress.)

Cost: no extra RAM (streamed either way) and ~the same peak disk (~2× the table
during the operation, same as staging+target coexisting today); it should be
*faster*, since it removes the redundant second 40M-row copy. Keep the split:
load logic in `utils.py`, Dagster metadata emission in the `assets.py` wrapper;
ad-hoc admin queries (`pg_stat_activity`, `pg_locks`) are ops tooling, not these
modules.

## TODO: carry the matched address strings in the table

Today `property_uprn_mapping` stores only `transaction_id`, `uprn`, `match_score`,
`match_type` — the IDs and the score, but **not the two address strings that were
compared**. So a FUZZY row can't be judged from the bridge table alone; you have
to join back to `land_registry_sales` and `epc_domestic_certificates` to see *why*
it matched (and whether a 0.90-ish score is a real hit or a false positive).

Make the matches self-explaining by carrying the address text on each row:

- Add columns for the **Land Registry address** (at least the normalised
  `addr_key` = PAON + Street, ideally raw `paon` / `street` / `postcode`) and the
  **EPC address** (normalised `addr_key` from `address1`, ideally raw `address1` /
  `postcode`). Populate them in `build_master_parquet` (`utils.py`) — both sides
  are already in scope at the exact/fuzzy joins; for the coverage rows fill only
  the side that exists (LR address on `UNMATCHED_LR`, EPC address on
  `UNMATCHED_UPRN`). Extend `MASTER_COLUMNS` / the DDL in `schema.py` to match.

Decide denormalise vs. view, because of the trade-off:
- **Denormalised columns** (what was asked) — instant to read, but widen a 40.6M-row
  table: ~40–60 bytes × 2 sides × 40.6M ≈ a few extra GB on top of the current
  ~6.9 GB, and the stored text can go stale if a source address is later corrected.
- **A read-time view** joining the bridge back to the two source tables — zero
  storage, always fresh, but pays the join on every query (and the EPC side is
  one-to-many: a UPRN can have several certificates with slightly different text).

Recommended: a **view** (e.g. `property_uprn_mapping_audit`) for eyeballing match
quality, and denormalised columns only if a downstream consumer needs the address
on the bridge row itself without a join. Either way it makes the FUZZY tier
auditable — the reason this came up.
