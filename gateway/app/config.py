"""Gateway configuration — read once from the environment at startup.

The DSN is the same ``POSTGRES_DSN`` the ingestion services use (see the repo
``.env``), so the API reads the very database the pipelines write. We only read
the environment here; the ``.env`` file is loaded opportunistically if
python-dotenv is installed, so running ``uvicorn`` from the repo root picks it
up in development without the dependency being mandatory in production (where
the variable is set for real).
"""

from __future__ import annotations

import os

try:  # optional dev convenience; absent in a bare production image
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:  # pragma: no cover - trivial fallback
    pass


def postgres_dsn() -> str:
    """The serving-database DSN, or a clear error if it isn't configured."""
    dsn = os.getenv("POSTGRES_DSN")
    if not dsn:
        raise RuntimeError(
            "POSTGRES_DSN is not set. Export it or add it to the repo .env "
            "(same DSN the ingestion services use), e.g. "
            "postgresql://user:pass@localhost:5433/property_discovery"
        )
    return dsn
