"""Root Dagster entry point — the single 'table of contents' Dagster loads.

This does NOT merge any data. It only merges the CODE definitions (assets, jobs,
schedules) from each ingestion service so Dagster can see them all in one place.
Each service still runs independently and writes to its own separate table.

We can't use `dg.Definitions.merge` directly: each service is self-contained and
declares its own `r2`/`postgres` resources (so its own tests can resolve its
jobs), and `merge` is identity-strict on shared resource keys — it rejects two
equal-but-distinct resource instances under the same key. So we combine the
component lists by hand and supply the shared resources once. The services are
configured from the same env vars, so a single `r2`/`postgres` pair serves both;
`epc` contributes its extra `epc` credential.

To add a service later: import it and fold its `defs` into the three `[*...]`
lists (and its resources into the mapping).
"""

from __future__ import annotations

import dagster as dg

from services.ingestion import epc, land_registry, os_open_uprn, reconciliation

_services = [land_registry.defs, epc.defs, reconciliation.defs, os_open_uprn.defs]

defs = dg.Definitions(
    assets=[a for d in _services for a in (d.assets or [])],
    jobs=[j for d in _services for j in (d.jobs or [])],
    schedules=[s for d in _services for s in (d.schedules or [])],
    # r2/postgres are identically configured across services; epc adds `epc`.
    # reconciliation and os_open_uprn reuse the same r2/postgres and add nothing.
    resources={
        **land_registry.defs.resources,
        **epc.defs.resources,
        **reconciliation.defs.resources,
        **os_open_uprn.defs.resources,
    },
)
