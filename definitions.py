"""Root Dagster entry point — the single 'table of contents' Dagster loads.

This does NOT merge any data. It only merges the CODE definitions (assets +
schedules) from each ingestion service so Dagster can see them all in one place.
Each service still runs independently and writes to its own separate table.

To add a service later: import its `defs` and add it to the merge() call.
"""

from __future__ import annotations

import dagster as dg

# Import the modules (not their `defs` names) so only ONE Definitions object
# lives at this module's scope — Dagster requires exactly one.
from services.ingestion import land_registry

# When epc is ready, uncomment:
# from services.ingestion import epc

defs = dg.Definitions.merge(
    land_registry.defs,
    # epc.defs,
)
