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