# AI-Native UK Property Search Engine Architecture

An enterprise-ready data architecture designed to merge **UK Land Registry Price Paid Data**, **EPC Ratings**, **Transport/Connectivity**, **Safety Metrics**, **Retail Amenities**, and **Environmental Risk Data** into a unified PostgreSQL/PostGIS database optimized for AI agentic retrieval and semantic search.

---

## 🛠️ Tech Stack & Extensions

* **Database:** PostgreSQL (v15+)
* **Spatial Processing:** [PostGIS](https://postgis.net/) (Spatial queries & distance calculations)
* **Vector Indexing:** [pgvector](https://github.com/pgvector/pgvector) (Semantic similarity search)
* **Core Identifier:** **UPRN** (Unique Property Reference Number) via OS Open UPRN / HM Land Registry Lookup

---

## 🏗️ Step 1: Core Property Data & Identifier (UPRN)

The **UPRN** serves as the universal single source of truth connecting all disparate UK datasets.

```sql
-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

-- Master property table anchored on UPRN
CREATE TABLE properties (
    uprn BIGINT PRIMARY KEY,
    address_line_1 TEXT NOT NULL,
    address_line_2 TEXT,
    town_city TEXT,
    postcode VARCHAR(10) NOT NULL,
    outcode VARCHAR(5), -- e.g., 'N1' for fast outward postcode filtering
    location GEOMETRY(Point, 4326), -- WGS84 Lat/Long coordinates
    
    -- Fast-lookup relational attributes
    current_epc_rating CHAR(1),
    property_type VARCHAR(20),
    last_sold_price NUMERIC,
    last_sold_date DATE,
    
    -- Embedded summary vector for semantic search
    summary_embedding vector(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Essential indexes for hybrid spatial + relational search
CREATE INDEX idx_properties_location ON properties USING GIST (location);
CREATE INDEX idx_properties_postcode ON properties (postcode);
CREATE INDEX idx_properties_outcode ON properties (outcode);
```

---

## 🔗 Step 2: Layered Data Architecture

### Layer 1: Energy Performance Certificates (EPC)
* **Source:** Ministry of Housing, Communities & Local Government (MHCLG)
* **Join Method:** Direct via UPRN (or fallback fuzzy-match on `postcode` + `address_line_1`).

```sql
CREATE TABLE property_epc (
    uprn BIGINT PRIMARY KEY REFERENCES properties(uprn),
    current_energy_rating CHAR(1),
    potential_energy_rating CHAR(1),
    current_energy_efficiency INT,
    potential_energy_efficiency INT,
    heating_cost_current NUMERIC,
    property_type VARCHAR(50),
    built_form VARCHAR(50),
    inspection_date DATE
);
```

---

### Layer 2: Transport & Accessibility
* **Source:** OpenStreetMap / TfL API / OpenTripPlanner
* **Strategy:** Pre-compute A-to-B transit metrics to avoid expensive real-time API calls during LLM queries.

```sql
CREATE TABLE property_transport_times (
    uprn BIGINT REFERENCES properties(uprn),
    destination_name VARCHAR(100), -- e.g., "Angel Station", "Canary Wharf"
    destination_type VARCHAR(50), -- "tube_station", "rail", "commercial_hub"
    mode VARCHAR(20),             -- "walk", "transit", "cycle"
    duration_minutes INT,
    distance_meters INT,
    PRIMARY KEY (uprn, destination_name, mode)
);

CREATE INDEX idx_transport_uprn_duration ON property_transport_times (uprn, duration_minutes);
```

---

### Layer 3: Neighborhood Safety & Crime Metrics
* **Source:** Data.police.uk (Mapped to LSOA or Postcode level)

```sql
CREATE TABLE locality_safety (
    postcode VARCHAR(10) PRIMARY KEY,
    lsoa_code VARCHAR(15),
    crime_rate_per_1000 NUMERIC,
    safety_rating_percentile INT, -- e.g., 85 = safer than 85% of UK
    anti_social_behaviour_count INT,
    violent_crime_count INT,
    last_updated DATE
);
```

---

### Layer 4: Retail & Grocery Amenities
* **Source:** OpenStreetMap / Ordnance Survey Points of Interest

```sql
CREATE TABLE property_amenities (
    uprn BIGINT REFERENCES properties(uprn),
    amenity_type VARCHAR(50), -- "supermarket", "park", "gym", "primary_school"
    brand VARCHAR(50),        -- "Waitrose", "Sainsbury's", "PureGym"
    distance_meters INT,
    walk_time_minutes INT,
    PRIMARY KEY (uprn, amenity_type, brand)
);
```

---

### Layer 5: Environmental & Geographic Risk
* **Source:** Environment Agency (Flood Risk Polygons)

```sql
CREATE TABLE property_environmental (
    uprn BIGINT PRIMARY KEY REFERENCES properties(uprn),
    flood_risk_level VARCHAR(20), -- "Low", "Medium", "High"
    air_quality_index INT,
    noise_level_decibels INT
);
```

---

## 🤖 Step 3: Making the Data AI-Native

AI Agents query databases through three main vectors: **Structured Filters (SQL)**, **Spatial Proximity (PostGIS)**, and **Semantic Preferences (Vector Similarity)**.

### 1. Document Store Pattern (`JSONB`) for LLM Context Injection
Synthesize all normalized relational tables into a single JSON profile per property. This enables an LLM agent to evaluate a property's full context in a single database read.

```sql
CREATE TABLE property_ai_documents (
    uprn BIGINT PRIMARY KEY REFERENCES properties(uprn),
    ai_summary_text TEXT NOT NULL, -- Text prompt used for generating vector embeddings
    full_profile JSONB NOT NULL   -- Structured JSON context for LLM window
);

-- JSON Indexing for rapid sub-field querying
CREATE INDEX idx_property_ai_json ON property_ai_documents USING GIN (full_profile);
```

#### Example `full_profile` JSON Payload:
```json
{
  "uprn": 10002334463,
  "address": "Flat 4, 12 Islington High St, London, N1 9DX",
  "pricing": {
    "last_sold": 650000,
    "date": "2024-03-15"
  },
  "epc": {
    "rating": "B",
    "potential": "A",
    "annual_heating_cost_gbp": 450
  },
  "transport": [
    {"destination": "Angel Station", "mode": "walk", "duration_min": 4},
    {"destination": "King's Cross", "mode": "transit", "duration_min": 12}
  ],
  "safety": {
    "crime_percentile": 72,
    "rating": "Moderate-High"
  },
  "retail": {
    "nearest_waitrose_meters": 250,
    "nearest_gym_meters": 400
  },
  "environment": {
    "flood_risk": "Very Low",
    "noise_level_db": 55
  }
}
```

---

### 2. PostGIS Functions Exposed as AI Tools
Expose custom PostgreSQL functions so an AI agent framework (e.g., LangChain, LlamaIndex, AutoGen) can call spatial radius queries as native function calls.

```sql
-- Function exposed to AI Agent Tool Call
CREATE OR REPLACE FUNCTION search_properties_near_location(
    lat DOUBLE PRECISION, 
    lng DOUBLE PRECISION, 
    radius_meters INT
)
RETURNS TABLE (
    uprn BIGINT,
    address_line_1 TEXT,
    postcode VARCHAR(10),
    distance_meters INT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.uprn,
        p.address_line_1,
        p.postcode,
        ST_Distance(
            p.location::geography, 
            ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography
        )::INT AS distance_meters
    FROM properties p
    WHERE ST_DWithin(
        p.location::geography, 
        ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography, 
        radius_meters
    )
    ORDER BY distance_meters ASC;
END;
$$ LANGUAGE plpgsql;
```

---

## 🚀 Query Pipeline Flow

```
+-----------------------------------------------------------------------+
|                         Natural Language Query                        |
| "Find me a flat near Angel Station under £700k, EPC B or higher,      |
|  within a 5 min walk to a Waitrose in a low crime neighborhood."     |
+-----------------------------------------------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                         AI Agent Router / LLM                         |
+-----------------------------------------------------------------------+
        /                           |                           \
       /                            |                            \
[Structured Filters]        [Spatial Tool Call]         [Vector Search]
- Price <= 700000           - search_properties_        - pgvector match on 
- EPC Rating in ('A','B')     near_location(...)          qualitative terms
       \                            |                            /
        \                           |                           /
         v                          v                          v
+-----------------------------------------------------------------------+
|                  PostgreSQL (Relational + Spatial + Vector)           |
+-----------------------------------------------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                       Final Aggregated JSON Payload                    |
+-----------------------------------------------------------------------+
```