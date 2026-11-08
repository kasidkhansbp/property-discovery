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

## Downstream mart: `mart_uprn_coverage_metrics`

A dashboard-facing coverage rollup, built by its **own** job
(`mart_coverage_metrics_job`, scheduled monthly a couple of hours after the
incremental reconciliation) so it can be refreshed independently of the bridge
build. One `GROUP BY` over `land_registry_sales` LEFT-JOINed to
`property_uprn_mapping` on `transaction_id` collapses every sale into one row per
`constituent_country` / `county` / `district` / `postcode_prefix` (the postcode
outward code, e.g. `EX4`, `CF36`), each carrying `total_land_registry_sales`,
`matched_uprn_count` (sales whose joined `uprn` is non-NULL), and
`coverage_percentage` (2 dp).

**The grouping geography comes from the sale, not the bridge.** The bridge's
`postcode` / `constituent_country` are EPC enrichment that only exists on
*matched* rows, so grouping on them would funnel every unmatched sale into a NULL
bucket and make coverage read as a meaningless 0%/100% split. The sale's own
`postcode` / `district` / `county` exist for every transaction, so grouping on
them gives true blended coverage per area; the bridge is joined on only for the
matched flag. `constituent_country` is derived England/Wales from the postcode
area (PPD is England & Wales only) — approximate at the border, fine for a
coverage view. The aggregation runs in Postgres (both sources are there and the
result is tiny) and swaps the new snapshot in atomically, so the dashboard never
re-scans the ~40M-row bridge and never sees a half-built table.

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
dagster job execute -f services/definitions.py -j reconciliation_full_job
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

## TODO: distribution of how many times a property is sold

We know per-area match coverage, but not how often individual properties change
hands. Build the **resale-frequency distribution**: group sales by property, count
the transactions per property, then roll those counts up into a histogram (how many
properties sold once, twice, three times, …). This is the input to churn / turnover
analytics (which areas and property types resell most).

- **Key the grouping on `uprn`, not address.** `property_uprn_mapping` already maps
  each `transaction_id` to a `uprn`, so join `land_registry_sales` to the bridge and
  `GROUP BY uprn` to get `sales_per_property = count(transaction_id)`. Grouping on the
  raw address strings instead would split the same property across spelling variants
  and inflate the "sold once" bucket.
- **Only matched sales can be counted per property.** `UNMATCHED_LR` sales have no
  `uprn`, so they can't be attributed to a property — report them as a separate
  "unattributable" figure rather than folding them into the "sold once" bucket, or
  the distribution reads low. (This is also why improving match coverage feeds
  directly into the accuracy of this metric.)
- **Mind the PPD scope** — Price Paid Data starts in 1995 and excludes some
  transfer types (e.g. many non-market / non-notified transfers), so a count is
  "sales since 1995 that PPD records," not a property's full history. Note that on
  the output so no one reads a `1` as "never resold."
- Natural home is a small mart (same pattern as `mart_uprn_coverage_metrics`): one
  row per `sales_count` bucket with `property_count`, optionally also keyed by
  geography (`constituent_country` / `county` / `district`) for per-area turnover.
