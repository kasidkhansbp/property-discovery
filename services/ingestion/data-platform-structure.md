# Property Discovery Platform

A modern, high-performance spatial data platform designed to ingest, reconcile, and enrich UK property transactions (HM Land Registry Price Paid Data) with Energy Performance Certificates (EPC), Ordnance Survey UPRNs, public transport networks (NaPTAN), and local neighborhood insights.

---

## 🏗️ Repository Architecture

The project is structured as a modular data and application platform, orchestrated via **Dagster** with analytics powered by **DuckDB** and **PostgreSQL/PostGIS**.

```text
property-discovery/
├── data/                       # Local data storage or landing directories
├── frontend/                   # UI application (React / Next.js)
├── gateway/                    # API Gateway layer
│   └── app/
│       └── routers/            # API endpoints & routing definitions
├── infra/                      # Infrastructure & routing configurations
│   └── osrm/                   # Open Source Routing Machine setup
├── services/                   # Core business logic & data services
│   ├── address_matcher/        # Address resolution & fuzzy matching engine
│   ├── ingestion/              # Dagster-powered data ingestion pipelines
│   │   ├── epc/                # Energy Performance Certificate data
│   │   ├── geolytix/           # Geospatial data ingestion
│   │   ├── gtfs/               # Public transit data ingestion
│   │   ├── inspire/            # INSPIRE spatial dataset ingestion
│   │   ├── land_registry/      # Price Paid Data (PPD) pipelines
│   │   ├── naptan/             # NaPTAN transit stop points data
│   │   └── osm/                # OpenStreetMap data processing
│   ├── profile_builder/        # Property profile aggregation
│   └── scoring/                # Valuation & land evaluation scoring models
├── shared/                     # Shared utilities, constants, and helpers
├── definitions.py              # Global Dagster repository / CodeLocation definitions
├── workspace.yaml              # Dagster workspace configuration
└── requirements.txt            # Python dependencies

# 1. The Core Tables (Master Datasets)
These tables ingest raw data directly from external sources and are updated whenever the underlying authorities release fresh data.

## land_registry_sales

What it stores: Historical and incoming property sales transactions (transaction_id, price, transfer date, postcode, address strings).

Update Frequency: Monthly (typically around the 23rd of every month via HMLR delta files handling additions, changes, and deletes).

## epc_certificates

What it stores: Energy performance ratings, floor areas, and characteristics tied directly to the uprn and certificate_number.

Update Frequency: Periodically / Quarterly (as MHCLG releases bulk domestic EPC data drops).

## os_open_uprn (or AddressBase)

What it stores: Master reference table containing every uprn and its authoritative spatial coordinates (x_coordinate, y_coordinate, latitude, longitude).

Update Frequency: Every 6 weeks (following the Ordnance Survey release schedule).

## transport_nodes (NaPTAN) & amenities_pois (OSM)

What it stores: Public transport stops/stations (NaPTAN) and local retail stores, parks, and points of interest (OpenStreetMap).

Update Frequency: Quarterly or Bi-Annually (static enough that monthly updates aren't necessary).

# 2. The Derived & Mapping Tables (The Bridge)
These tables are generated or refreshed by your internal data pipeline after the core tables are loaded.

## property_uprn_mapping

What it stores: The definitive cross-reference bridge connecting Land Registry's transaction_id to the property's uprn (including exact matches and fuzzy/fallback match tiers).

Update Frequency: Monthly (triggered immediately after the Land Registry monthly delta ingestion runs).

## properties_master_spatial

What it stores: The unified property profile table. It merges the Land Registry sale details, EPC energy metrics, UPRN identifier, and exact GPS coordinates (latitude, longitude).

Update Frequency: Monthly (refreshed downstream of the UPRN mapping step).

## property_transit_metrics (Isochrones & Distances)

What it stores: Pre-calculated distances and travel times from each property UPRN to the nearest train stations or city centers (e.g., 30-minute commute to London).

Update Frequency: Monthly / Triggered on UPRN refresh (computed via spatial tools like DuckDB Spatial or PostGIS).