"""Live progress monitor for the ingestion pipelines' Postgres loads.

The Dagster UI (`dagster dev`) is the primary way to see jobs run: it shows every
run's steps, logs, timings, and the per-asset metadata. Its blind spot is the
*inside* of a single long-running SQL statement — a 40M-row INSERT shows only the
step clock ticking. This script fills that gap, and it is **generic across every
job**: land_registry, epc, and reconciliation all drive Postgres the same way
(DuckDB's postgres extension for the staging COPY, psycopg for the merge), so one
monitor covers them all.

It is strictly **read-only ops tooling** — it never touches the pipeline modules
and never blocks: a short `lock_timeout`/`statement_timeout` plus autocommit mean
a query against an exclusively-locked table (e.g. a full-rebuild `TRUNCATE`) fails
fast and is reported as "locked", rather than hanging the monitor.

Usage (from the repo root, so .env is found):
    python scripts/job_monitor.py            # one snapshot
    python scripts/job_monitor.py --watch    # refresh every 3s until Ctrl-C
    python scripts/job_monitor.py --watch --interval 5
    python scripts/job_monitor.py --dsn postgresql://...   # override .env
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime

import psycopg

# Known pipeline tables -> which job/service they belong to. Used to tag each
# running query so you can tell at a glance which pipeline is loading.
_TABLE_OWNER = {
    "land_registry_sales": "land_registry",
    "epc_domestic_certificates": "epc",
    "property_uprn_mapping": "reconciliation",
}


def _load_dsn(cli_dsn: str | None) -> str:
    """Resolve the Postgres DSN: explicit --dsn, else env, else parse .env."""
    if cli_dsn:
        return cli_dsn
    if os.environ.get("POSTGRES_DSN"):
        return os.environ["POSTGRES_DSN"]
    env_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            m = re.match(r"\s*POSTGRES_DSN\s*=\s*(.+?)\s*$", line)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    sys.exit("No POSTGRES_DSN found (set it in .env, the environment, or pass --dsn).")


def _tag(query: str) -> str:
    """Label a query with the pipeline it belongs to, by target table name."""
    q = query.lower()
    for table, owner in _TABLE_OWNER.items():
        if table in q:
            return owner
    return "-"


def _fmt_age(td) -> str:
    """Compact H:MM:SS for a timedelta (or '-' if None)."""
    if td is None:
        return "-"
    s = int(td.total_seconds())
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _q(cur, sql: str, params=()):
    """Run one read query, returning rows; never raise (autocommit + timeouts)."""
    try:
        cur.execute(sql, params)
        return cur.fetchall()
    except Exception as e:  # lock_timeout / statement_timeout / etc.
        return [("__error__", str(e).splitlines()[0])]


def _wal_sample(cur) -> tuple[str, float]:
    """Current WAL write position + a wall-clock stamp — the two-point baseline."""
    cur.execute("SELECT pg_current_wal_lsn()::text;")
    return cur.fetchone()[0], time.monotonic()


def snapshot(cur, prev: tuple[str, float]) -> tuple[str, float]:
    """Print one frame; return the WAL sample to diff against on the next call.

    `prev` is the WAL (lsn, time) captured last frame; the difference to now is
    the bytes Postgres wrote in between — the lock-free "is it moving?" signal.
    """
    print(f"\n=== pipeline load monitor @ {datetime.now():%Y-%m-%d %H:%M:%S} ===")

    # 0) WAL write rate — bytes written since the previous sample. Any role, no
    #    lock: nonzero & steady = actively writing; zero = idle/stalled.
    cur_lsn, cur_t = _wal_sample(cur)
    d = _q(cur, "SELECT pg_wal_lsn_diff(%s::pg_lsn, %s::pg_lsn)::bigint;", (cur_lsn, prev[0]))
    dt = max(cur_t - prev[1], 1e-6)
    print("\n-- WAL write rate (is it moving?) --")
    if d and d[0][0] == "__error__":
        print(f"   unavailable: {d[0][1]}")
    else:
        wrote = d[0][0] or 0
        verdict = "writing (a load is moving)" if wrote > 0 else "NO WAL (idle or stalled)"
        print(f"   {wrote / 1e6:8.1f} MB in {dt:4.1f}s   ({wrote / dt / 1e6:5.1f} MB/s)   <- {verdict}")

    # 1) Active statements on this database (any job's load shows up here).
    rows = _q(
        cur,
        """
        SELECT pid, usename, state, wait_event_type, wait_event,
               now() - query_start AS age,
               left(regexp_replace(query, '\\s+', ' ', 'g'), 70) AS q
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND pid <> pg_backend_pid()
          AND state <> 'idle'
        ORDER BY query_start NULLS LAST;
        """,
    )
    print("\n-- active statements --")
    if not rows:
        print("   (none - no job is currently running a query)")
    elif rows[0][0] == "__error__":
        print(f"   query failed: {rows[0][1]}")
    else:
        print(f"   {'job':<14} {'pid':>6} {'state':<9} {'wait':<18} {'elapsed':>9}  query")
        for pid, user, state, wt, we, age, q in rows:
            wait = f"{wt}/{we}" if wt else "-"
            print(f"   {_tag(q):<14} {pid:>6} {state:<9} {wait:<18} {_fmt_age(age):>9}  {q}")

    # 2) COPY progress (DuckDB's staging bulk-load registers here; tuple-level %).
    rows = _q(
        cur,
        """
        SELECT c.relname,
               p.tuples_processed,
               p.tuples_excluded,
               p.bytes_processed,
               p.bytes_total
        FROM pg_stat_progress_copy p
        LEFT JOIN pg_class c ON c.oid = p.relid;
        """,
    )
    copy_rows = [r for r in rows if r and r[0] != "__error__"]
    if copy_rows:
        print("\n-- COPY progress --")
        for relname, tproc, texcl, bproc, btotal in copy_rows:
            pct = f"{bproc / btotal * 100:5.1f}%" if btotal else "  ?  "
            print(
                f"   {relname or '?':<34} {tproc or 0:>14,} tuples  "
                f"{(bproc or 0) / 1e6:9.1f} MB  {pct}"
            )

    # 3) Anything blocked on a lock, and who holds it.
    rows = _q(
        cur,
        """
        SELECT pid, pg_blocking_pids(pid) AS blocked_by,
               left(regexp_replace(query, '\\s+', ' ', 'g'), 50) AS q
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND cardinality(pg_blocking_pids(pid)) > 0;
        """,
    )
    blocked = [r for r in rows if r and r[0] != "__error__"]
    if blocked:
        print("\n-- blocked on locks --")
        for pid, by, q in blocked:
            print(f"   pid {pid} blocked by {by}: {q}")

    # 4) Target table sizes (lock-safe: a table under a full-rebuild TRUNCATE's
    #    ACCESS EXCLUSIVE lock is reported as "locked", not waited on).
    print("\n-- target tables --")
    for table, owner in _TABLE_OWNER.items():
        r = _q(
            cur,
            "SELECT pg_size_pretty(pg_total_relation_size(%s)), "
            "       (SELECT reltuples::bigint FROM pg_class WHERE relname = %s)",
            (table, table),
        )
        if r and r[0][0] == "__error__":
            print(f"   {owner:<14} {table:<30} locked (load in progress)")
        elif r and r[0][0] is None:
            print(f"   {owner:<14} {table:<30} (not created yet)")
        else:
            size, est = r[0]
            print(f"   {owner:<14} {table:<30} {size:>10}  ~{est or 0:,} rows (est)")

    return cur_lsn, cur_t


def main() -> None:
    ap = argparse.ArgumentParser(description="Live monitor for pipeline Postgres loads.")
    ap.add_argument("--dsn", help="Postgres DSN (default: POSTGRES_DSN / .env)")
    ap.add_argument("--watch", action="store_true", help="refresh continuously")
    ap.add_argument("--interval", type=float, default=3.0, help="refresh seconds (--watch)")
    args = ap.parse_args()

    with psycopg.connect(_load_dsn(args.dsn), connect_timeout=5) as conn:
        conn.autocommit = True  # each stmt independent; a timeout can't poison the next
        with conn.cursor() as cur:
            # Never block: fail fast on a locked relation and move on.
            cur.execute("SET lock_timeout = '500ms';")
            cur.execute("SET statement_timeout = '5s';")
            # A WAL rate needs two points over time, so take a baseline, wait one
            # interval, then print. Each printed frame reports the rate since the
            # frame before it.
            prev = _wal_sample(cur)
            if not args.watch:
                time.sleep(args.interval)
                snapshot(cur, prev)
                return
            try:
                while True:
                    time.sleep(args.interval)
                    print("\033[2J\033[H", end="")  # clear screen for a live view
                    prev = snapshot(cur, prev)
                    print(f"\n(refreshing every {args.interval:g}s - Ctrl-C to stop)")
            except KeyboardInterrupt:
                print("\nstopped.")


if __name__ == "__main__":
    main()
