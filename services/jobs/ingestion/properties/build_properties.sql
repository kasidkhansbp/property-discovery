-- One-time build of `properties`: one row per UPRN.
--
--   * Base: every UPRN in os_open_uprn, with its coordinates.
--   * Address + attributes: the latest EPC certificate per UPRN (by
--     lodgement_date, ties broken by certificate_number). UPRNs with no EPC
--     certificate keep NULL address fields.
--   * Address text is upper-cased, trimmed, inner whitespace collapsed, and
--     empty parts dropped before joining with ', '.
--
-- Run with psql (it takes minutes, so not from Railway's Query tab):
--   psql "$DATABASE_URL" -f build_properties.sql
-- Re-runnable: it empties the table first, all in one transaction, so a failed
-- run leaves the previous contents in place. Run create_properties_indexes.sql
-- afterwards.

\timing on

BEGIN;

TRUNCATE properties;

INSERT INTO properties (
    uprn, full_address, address_line_1, posttown, postcode, postcode_clean,
    country, property_type, built_form, uprn_source, address_source,
    search_text, latitude, longitude, x_coordinate, y_coordinate, updated_at
)
WITH epc_latest AS (
    -- Latest certificate per UPRN. EPC stores uprn as text; only all-digit
    -- values that fit a bigint are usable.
    SELECT DISTINCT ON (uprn::bigint)
           uprn::bigint AS uprn,
           address1, address2, address3, posttown, postcode,
           country, property_type, built_form, uprn_source
    FROM epc_domestic_certificates
    WHERE uprn ~ '^[0-9]{1,18}$'
    ORDER BY uprn::bigint, lodgement_date DESC NULLS LAST, certificate_number DESC
),
cleaned AS (
    -- Upper-case, trim, collapse runs of whitespace; '' becomes NULL.
    SELECT uprn,
           nullif(btrim(regexp_replace(upper(address1), '\s+', ' ', 'g')), '') AS a1,
           nullif(btrim(regexp_replace(upper(address2), '\s+', ' ', 'g')), '') AS a2,
           nullif(btrim(regexp_replace(upper(address3), '\s+', ' ', 'g')), '') AS a3,
           nullif(btrim(regexp_replace(upper(posttown), '\s+', ' ', 'g')), '') AS posttown,
           nullif(btrim(regexp_replace(upper(postcode), '\s+', ' ', 'g')), '') AS postcode,
           country, property_type, built_form, uprn_source
    FROM epc_latest
),
addressed AS (
    SELECT c.*,
           nullif(concat_ws(', ', a1, a2, a3), '') AS address_line_1
    FROM cleaned c
),
epc AS (
    SELECT a.*,
           nullif(concat_ws(', ', address_line_1, posttown, postcode), '') AS full_address
    FROM addressed a
)
SELECT o.uprn,
       e.full_address,
       e.address_line_1,
       e.posttown,
       e.postcode,
       nullif(regexp_replace(e.postcode, '\s', '', 'g'), '')          AS postcode_clean,
       e.country,
       e.property_type,
       e.built_form,
       e.uprn_source,
       CASE WHEN e.full_address IS NOT NULL THEN 'EPC' END              AS address_source,
       nullif(btrim(regexp_replace(e.full_address, '[^A-Z0-9]+', ' ', 'g')), '') AS search_text,
       o.latitude,
       o.longitude,
       o.x_coordinate,
       o.y_coordinate,
       now()                                                            AS updated_at
FROM os_open_uprn o
LEFT JOIN epc e ON e.uprn = o.uprn;

COMMIT;

ANALYZE properties;
