"""Memory-bounded DuckDB connections for the ingestion pipelines.

Every pipeline (epc, land_registry, os_open_uprn, reconciliation) used to open a
bare ``duckdb.connect()`` and point it at R2. That is unsafe in a container:
DuckDB sizes its default memory budget (80% of RAM) from the HOST machine, not
the container's cgroup cap, so inside an 8 GB Railway service it believes it has
tens of GB, never throttles or spills, and is OOM-killed mid-query. The kill
takes the whole container with it — no traceback, no Dagster STEP_FAILURE, no
alert — the log just stops. (That is exactly how the 2026-11 EPC run died.)

``bounded_duckdb`` is the one place that opens a connection, so every pipeline
gets the same guard rails:

  * ``memory_limit`` well below the container cap, leaving headroom for Python,
    boto3 and the httpfs S3 upload buffers that live outside DuckDB's budget.
  * a modest ``threads`` count — fewer parallel CSV readers, lower peak memory;
    these steps are I/O-bound anyway.
  * ``preserve_insertion_order = false`` so big COPY / INSERT ... SELECT
    statements stream instead of buffering input to keep row order. Nothing here
    depends on implicit order: every ordering that matters is an explicit
    ORDER BY / window clause, and the Postgres loads de-dup with DISTINCT ON.
  * a private spill directory (``temp_directory``) so DuckDB can offload sorts
    and hash joins to disk when it hits the limit, instead of failing.
  * optionally a FILE-BACKED database (``on_disk=True``). An in-memory database
    can spill *intermediates* but cannot evict its own base tables, so a step
    that materialises big tables (reconciliation: ``CREATE TABLE ... AS SELECT``
    over all of land_registry + epc) must be file-backed for the cap to be
    honoured rather than merely turning the kill into an OOM error.

Both limits are env-tunable so a bigger (or smaller) service can be matched
from the Railway dashboard without a code change:

  DUCKDB_MEMORY_LIMIT   default "5GB"  (sized for an 8 GB container)
  DUCKDB_THREADS        default "4"
"""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from typing import Iterator, Protocol

import duckdb

DUCKDB_MEMORY_LIMIT = os.environ.get("DUCKDB_MEMORY_LIMIT", "5GB")
DUCKDB_THREADS = int(os.environ.get("DUCKDB_THREADS", "4"))


class R2Like(Protocol):
    """Anything that can point a DuckDB connection at R2 over httpfs.

    Each pipeline carries its own R2Resource class; they all expose this method.
    """

    def configure_duckdb(self, con: duckdb.DuckDBPyConnection) -> None: ...


def _fwd(path: str) -> str:
    """DuckDB wants forward slashes in paths, even on Windows."""
    return path.replace("\\", "/")


@contextmanager
def bounded_duckdb(
    r2: R2Like,
    *,
    work_dir: str | None = None,
    on_disk: bool = False,
    progress_bar: bool = False,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Open a memory-bounded DuckDB connection pointed at R2; always close it.

    ``work_dir``: where the spill directory (and, with ``on_disk``, the database
    file) live. Defaults to a fresh temp dir that is removed on exit; if the
    caller passes its own, the caller owns its cleanup.
    ``on_disk``: open a file-backed database instead of in-memory, so base
    tables can be paged to disk under ``memory_limit`` (see module docstring).
    ``progress_bar``: print DuckDB's live progress bar to stdout for
    long-running statements (Dagster captures it into the step's compute log).
    """
    own_dir = work_dir is None
    base = work_dir or tempfile.mkdtemp(prefix="duckdb_")
    spill_dir = os.path.join(base, "duckdb_spill")
    os.makedirs(spill_dir, exist_ok=True)

    database = os.path.join(base, "duckdb.db") if on_disk else ":memory:"
    con = duckdb.connect(database)
    try:
        r2.configure_duckdb(con)
        con.execute(f"SET memory_limit = '{DUCKDB_MEMORY_LIMIT}';")
        con.execute(f"SET threads = {DUCKDB_THREADS};")
        con.execute("SET preserve_insertion_order = false;")
        con.execute(f"SET temp_directory = '{_fwd(spill_dir)}';")
        if progress_bar:
            # progress_bar_time=0 shows the bar immediately rather than after a
            # delay; useful for the single blocking joins/COPYs in reconciliation.
            con.execute("SET enable_progress_bar = true;")
            con.execute("SET enable_progress_bar_print = true;")
            con.execute("SET progress_bar_time = 0;")
        yield con
    finally:
        con.close()
        if own_dir:
            shutil.rmtree(base, ignore_errors=True)
