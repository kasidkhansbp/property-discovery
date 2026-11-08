"""Job for the OS Open UPRN pipeline.

One job, no schedule. OS Open UPRN is republished by Ordnance Survey roughly
every six weeks; this job downloads the current release from the OS Downloads
API, cleans it, and diff-merges it into Postgres. It's launched by hand (the
download step skips cheaply when the release md5 is unchanged, so running it when
nothing is new is harmless).

(If you ever want it to run unattended, the natural upgrade is a time-based
schedule — say weekly — relying on the md5 skip to no-op between releases.)
"""

from __future__ import annotations

import dagster as dg

from . import assets

# Manually triggered: download -> clean -> load the current release.
os_open_uprn_load_job = dg.define_asset_job(
    name="os_open_uprn_load_job",
    selection=dg.AssetSelection.assets(
        assets.os_open_uprn_raw_zip,
        assets.os_open_uprn_clean_parquet,
        assets.os_open_uprn_loaded_to_postgres,
    ),
)
