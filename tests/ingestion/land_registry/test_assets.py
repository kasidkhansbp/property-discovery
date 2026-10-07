"""Tests for the PPD asset factory and its two wired chains.

`_build_ppd_assets` is a factory that emits a raw -> clean -> load trio for one
chain. These tests check the asset keys, the raw->clean->load dependency wiring,
and the per-chain config (URL, object-key prefix, delete handling) without
running any step — so no network, DuckDB, or Postgres is touched.
"""

from __future__ import annotations

import re

import dagster as dg

from services.ingestion.land_registry import assets


def test_stamp_is_an_iso_utc_date():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", assets._stamp())


def test_source_urls_point_at_the_expected_hmlr_files():
    assert assets.PPD_COMPLETE_URL.endswith("/pp-complete.csv")
    assert assets.PPD_MONTHLY_URL.endswith("/pp-monthly-update-new-version.csv")


def _trio(chain: str, url: str, handle_deletes: bool):
    return assets._build_ppd_assets(chain, url, handle_deletes=handle_deletes)


def test_factory_names_the_three_assets_per_chain():
    raw, clean, load = _trio("complete", assets.PPD_COMPLETE_URL, False)
    assert raw.key == dg.AssetKey("ppd_complete_raw_csv")
    assert clean.key == dg.AssetKey("ppd_complete_clean_parquet")
    assert load.key == dg.AssetKey("ppd_complete_loaded_to_postgres")


def test_clean_depends_on_raw_and_load_depends_on_clean():
    raw, clean, load = _trio("monthly", assets.PPD_MONTHLY_URL, True)
    assert raw.key in clean.dependency_keys
    assert clean.key in load.dependency_keys


def test_every_asset_is_in_the_land_registry_group():
    for node in _trio("complete", assets.PPD_COMPLETE_URL, False):
        assert set(node.group_names_by_key.values()) == {"land_registry"}


def test_exported_complete_and_monthly_assets_have_distinct_keys():
    keys = {
        assets.ppd_complete_raw_csv.key,
        assets.ppd_complete_clean_parquet.key,
        assets.ppd_complete_loaded_to_postgres.key,
        assets.ppd_monthly_raw_csv.key,
        assets.ppd_monthly_clean_parquet.key,
        assets.ppd_monthly_loaded_to_postgres.key,
    }
    # No overlap between the two chains -> six distinct asset keys.
    assert len(keys) == 6
