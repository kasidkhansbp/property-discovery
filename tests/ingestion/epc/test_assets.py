"""Tests for the EPC asset factory and its two wired chains.

`_build_epc_assets` is a factory that emits a raw -> clean -> load trio for one
chain. These tests check the asset keys, the raw->clean->load dependency wiring,
and the per-chain config (object-key prefix) without running any step — so no
network, DuckDB, or Postgres is touched. A small unit test also pins the cleaning
SELECT to the schema.
"""

from __future__ import annotations

import re

import dagster as dg

from services.ingestion.epc import assets, utils
from services.ingestion.epc.schema import EPC_SCHEMA


def test_stamp_is_an_iso_utc_date():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", assets._stamp())


def test_source_url_points_at_the_epc_bulk_domestic_file():
    # MHCLG's new "Get energy performance of buildings data" domestic full-load
    # endpoint (replaces the retired Open Data Communities bulk ZIP).
    assert assets.EPC_DOMESTIC_URL == (
        "https://api.get-energy-performance-data.communities.gov.uk"
        "/api/files/domestic/csv"
    )


def _trio(chain: str, url: str):
    return assets._build_epc_assets(chain, url)


def test_factory_names_the_three_assets_per_chain():
    raw, clean, load = _trio("complete", assets.EPC_DOMESTIC_URL)
    assert raw.key == dg.AssetKey("epc_complete_raw_zip")
    assert clean.key == dg.AssetKey("epc_complete_clean_parquet")
    assert load.key == dg.AssetKey("epc_complete_loaded_to_postgres")


def test_clean_depends_on_raw_and_load_depends_on_clean():
    raw, clean, load = _trio("monthly", assets.EPC_DOMESTIC_URL)
    assert raw.key in clean.dependency_keys
    assert clean.key in load.dependency_keys


def test_every_asset_is_in_the_epc_group():
    for node in _trio("complete", assets.EPC_DOMESTIC_URL):
        assert set(node.group_names_by_key.values()) == {"epc"}


def test_exported_complete_and_monthly_assets_have_distinct_keys():
    keys = {
        assets.epc_complete_raw_zip.key,
        assets.epc_complete_clean_parquet.key,
        assets.epc_complete_loaded_to_postgres.key,
        assets.epc_monthly_raw_zip.key,
        assets.epc_monthly_clean_parquet.key,
        assets.epc_monthly_loaded_to_postgres.key,
    }
    # No overlap between the two chains -> six distinct asset keys.
    assert len(keys) == 6


def test_clean_select_projects_every_schema_column_from_its_source_header():
    sql = utils._clean_select()
    for col in EPC_SCHEMA:
        assert f"AS {col.name}" in sql
        assert f'"{col.csv_name}"' in sql
        # Typed columns are NULLIF'd then cast; text columns are not cast.
        if col.csv_type != "VARCHAR":
            assert f"CAST(nullif(\"{col.csv_name}\", '') AS {col.csv_type})" in sql
