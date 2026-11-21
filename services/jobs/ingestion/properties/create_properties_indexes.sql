-- Search indexes for `properties`. Run after build_properties.sql has filled the
-- table: building an index once over loaded rows is much faster than updating
-- it on every insert.
--
--   psql "$DATABASE_URL" -f create_properties_indexes.sql
--
-- Each build takes minutes on ~40M rows, so run it from psql (Railway Console),
-- not the 45-second Query tab. Partial indexes skip the UPRNs with no address.

\timing on

-- Postcode search: exact match and "starts with" (LIKE 'SW1A1%').
CREATE INDEX IF NOT EXISTS properties_postcode_clean_idx
    ON properties (postcode_clean text_pattern_ops)
    WHERE postcode_clean IS NOT NULL;

-- Address search: "contains" (ILIKE '%BAKER ST%') and typo-tolerant similarity.
-- Needs the pg_trgm extension (enabled by migration 0003).
CREATE INDEX IF NOT EXISTS properties_search_text_trgm_idx
    ON properties USING gin (search_text gin_trgm_ops)
    WHERE search_text IS NOT NULL;

ANALYZE properties;

-- Both should show indisvalid = t.
SELECT indexrelid::regclass AS index_name, indisvalid
FROM pg_index
WHERE indrelid = 'properties'::regclass;
