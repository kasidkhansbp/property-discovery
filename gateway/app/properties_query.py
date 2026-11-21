"""Pure SQL builders for the ``properties`` read API.

Like ``query.py`` and ``quality_query.py``, nothing here touches FastAPI or a
live database: each function returns ``(sql, params)`` so the paging rules are
unit-testable without Postgres.

``properties`` is large (~40M rows, one per UPRN), which shapes two choices:

  * **Rows are always ordered by ``uprn``** (the primary key), so every page is
    an index range scan and paging is deterministic.
  * **Keyset paging only.** A page is "the next ``limit`` rows after
    ``after_uprn``", an index seek that costs the same on page 1 and page
    800,000. There is deliberately no ``offset``: Postgres walks every skipped
    row, so deep offsets take seconds. Previous is handled client-side by
    remembering the cursors already visited.
  * **The total is an estimate.** An exact ``count(*)`` over 40M rows takes
    seconds on every request; the planner's ``reltuples`` statistic is instant
    and accurate to well under 1% after ``ANALYZE`` (which the build script
    runs). Good enough for "page X of Y".

Same safety rules as the other builders: identifiers come only from the shared
model (``PROPERTIES_TABLE`` / ``PROPERTIES_COLUMNS``), values are always bound
as ``%s`` parameters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from shared.db.schema import (
    EPC_TABLE,
    LAND_REGISTRY_TABLE,
    PROPERTIES_COLUMNS,
    PROPERTIES_TABLE,
    UPRN_MAPPING_TABLE,
)

DEFAULT_LIMIT: int = 50
MAX_LIMIT: int = 200
_ORDER_COLUMN: str = "uprn"


def build_properties_page_query(
    *,
    limit: int = DEFAULT_LIMIT,
    after_uprn: int | None = None,
) -> tuple[str, list[Any]]:
    """SQL + params for one page of ``properties``, ordered by ``uprn``.

    With ``after_uprn`` set, returns the ``limit`` rows whose uprn is greater
    than it; without it, the first page. Raises ``ValueError`` for an
    out-of-range limit.
    """
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be 1..{MAX_LIMIT}, got {limit}")

    params: list[Any] = []
    where = ""
    if after_uprn is not None:
        where = f"WHERE {_ORDER_COLUMN} > %s\n"
        params.append(after_uprn)

    sql = (
        f"SELECT {', '.join(PROPERTIES_COLUMNS)}\n"
        f"FROM {PROPERTIES_TABLE}\n"
        f"{where}"
        f"ORDER BY {_ORDER_COLUMN}\n"
        f"LIMIT %s"
    )
    params.append(limit)
    return sql, params


def build_properties_estimate_query() -> tuple[str, list[Any]]:
    """SQL + params for the planner's row-count estimate of ``properties``.

    ``reltuples`` is -1 for a table that has never been vacuumed/analysed, so
    that case is clamped to 0 rather than reported as a negative total.
    """
    sql = (
        "SELECT greatest(reltuples, 0)::bigint AS estimated_total\n"
        "FROM pg_class\n"
        "WHERE oid = to_regclass(%s)"
    )
    return sql, [PROPERTIES_TABLE]


# --------------------------------------------------------------------------- #
# Search                                                                      #
# --------------------------------------------------------------------------- #
# ``GET /properties/search?q=...`` takes one free-form box, decides what the
# user typed (``classify_search``), then builds the SQL for that mode
# (``build_search_query``). Every mode uses an index that already exists (see
# create_properties_indexes.sql):
#
#   mode                example input              index
#   ------------------  -------------------------  ------------------------------
#   uprn                100023336956               primary key
#   postcode            SW1A 1AA / SW1A 1 / SW1A   properties_postcode_clean_idx
#   postcode_and_text   flat 3 12 high st SW1A1AA  postcode index, text ranked
#   text                12 baker street london     properties_search_text_trgm_idx
#
# Phase 2 (planned) replaces only ``_build_text_search`` with a tsvector query
# on an expression index; the endpoint and response shape stay the same.

SearchMode = Literal["uprn", "postcode", "postcode_and_text", "text"]

DEFAULT_SEARCH_LIMIT: int = 20
MAX_SEARCH_LIMIT: int = 100
# Shortest text query (letters/digits only, spaces ignored) that is accepted.
MIN_TEXT_QUERY_LENGTH: int = 3
# Text mode ranks at most this many matching rows, so a common word matching
# millions of rows still returns in bounded time. Phase 1 trade-off: when more
# rows match, the best match can fall outside this set.
TEXT_CANDIDATE_LIMIT: int = 500
# UPRNs are at most 12 digits.
_MAX_UPRN_DIGITS: int = 12

# A UK postcode: outcode (A9, A9A, A99, AA9, AA9A, AA99) + incode (9AA).
_OUTCODE = r"[A-Z]{1,2}[0-9][A-Z0-9]?"
_INCODE = r"[0-9][A-Z]{2}"
_FULL_POSTCODE_RE = re.compile(rf"^({_OUTCODE}) ?({_INCODE})$")
# An outcode with an optional partial incode: 'SW1A', 'SW1A 1', 'SW1A 1A'.
_PARTIAL_POSTCODE_RE = re.compile(rf"^({_OUTCODE})(?: ([0-9][A-Z]?))?$")
# A full postcode written as tokens inside a longer address.
_EMBEDDED_POSTCODE_RE = re.compile(rf"(?:^| )({_OUTCODE}) ?({_INCODE})(?= |$)")


def normalise_search_text(q: str) -> str:
    """Normalise input the same way build_properties.sql normalises search_text.

    Upper-case; every run of non-alphanumerics becomes one space; trimmed. Query
    tokens then line up with the stored tokens.
    """
    return re.sub(r"[^A-Z0-9]+", " ", q.upper()).strip()


@dataclass(frozen=True)
class ClassifiedSearch:
    """What a search-box input was understood to be."""

    mode: SearchMode
    uprn: int | None = None
    # postcode / postcode_and_text: exact compact postcode, or a LIKE pattern.
    postcode_exact: str | None = None
    postcode_pattern: str | None = None
    # text / postcode_and_text: the query's words, outside any postcode. Text
    # mode requires each to appear in search_text.
    tokens: tuple[str, ...] = field(default_factory=tuple)
    # text / postcode_and_text: those words as one string, for similarity
    # ranking.
    text: str | None = None


def classify_search(q: str) -> ClassifiedSearch:
    """Decide which search mode ``q`` needs. Raises ``ValueError`` if unusable.

    Checked in order:
      1. digits only                -> uprn
      2. a full postcode            -> postcode (exact)
      3. outcode [+ partial incode] -> postcode (pattern)
      4. contains a full postcode   -> postcode_and_text
      5. anything else              -> text; needs a word of 3+ characters,
         because the trigram index can't narrow on shorter ones
    """
    norm = normalise_search_text(q)
    if not norm:
        raise ValueError("search query is empty")

    compact = norm.replace(" ", "")
    if compact.isdigit():
        if len(compact) > _MAX_UPRN_DIGITS:
            raise ValueError(f"a UPRN has at most {_MAX_UPRN_DIGITS} digits")
        return ClassifiedSearch(mode="uprn", uprn=int(compact))

    if m := _FULL_POSTCODE_RE.match(norm):
        return ClassifiedSearch(mode="postcode", postcode_exact=m[1] + m[2])

    if m := _PARTIAL_POSTCODE_RE.match(norm):
        outcode, incode_prefix = m[1], m[2]
        if incode_prefix is None:
            # 'SW1' alone: plain prefix, so the results keep matching while the
            # user types towards 'SW1A' (it also matches SW10-SW19).
            pattern = outcode + "%"
        else:
            # A space was typed, so the outcode is exact: 'SW1A 1' means
            # SW1A1 + two more characters, never a longer outcode.
            pattern = outcode + incode_prefix + "_" * (3 - len(incode_prefix))
        return ClassifiedSearch(mode="postcode", postcode_pattern=pattern)

    if m := _EMBEDDED_POSTCODE_RE.search(norm):
        rest = (norm[: m.start()] + " " + norm[m.end():]).split()
        return ClassifiedSearch(
            mode="postcode_and_text",
            postcode_exact=m[1] + m[2],
            tokens=tuple(rest),
            text=" ".join(rest),
        )

    tokens = tuple(norm.split())
    if len(compact) < MIN_TEXT_QUERY_LENGTH or max(map(len, tokens)) < 3:
        raise ValueError(
            "search text too short: type a word of 3+ characters, a postcode, "
            "or a UPRN"
        )
    return ClassifiedSearch(mode="text", tokens=tokens, text=norm)


def _like_clauses(tokens: tuple[str, ...]) -> tuple[list[str], list[Any]]:
    """One ``search_text LIKE '%TOKEN%'`` per token.

    Tokens come from ``normalise_search_text`` (A-Z and 0-9 only), so they can't
    contain the LIKE wildcards ``%`` or ``_`` and need no escaping.
    """
    return ["search_text LIKE %s"] * len(tokens), [f"%{t}%" for t in tokens]


def build_search_query(
    search: ClassifiedSearch, *, limit: int = DEFAULT_SEARCH_LIMIT
) -> tuple[str, list[Any]]:
    """SQL + params for a classified search.

    Fetches ``limit + 1`` rows: if the extra row comes back, more results exist
    (``has_more``). Raises ``ValueError`` for an out-of-range limit.
    """
    if not 1 <= limit <= MAX_SEARCH_LIMIT:
        raise ValueError(f"limit must be 1..{MAX_SEARCH_LIMIT}, got {limit}")
    fetch = limit + 1
    cols = ", ".join(PROPERTIES_COLUMNS)

    if search.mode == "uprn":
        sql = f"SELECT {cols}\nFROM {PROPERTIES_TABLE}\nWHERE uprn = %s\nLIMIT %s"
        return sql, [search.uprn, fetch]

    if search.mode == "postcode":
        if search.postcode_exact is not None:
            where, value = "postcode_clean = %s", search.postcode_exact
        else:
            where, value = "postcode_clean LIKE %s", search.postcode_pattern
        # ``USING ~<~`` sorts with the text_pattern_ops operator class, the same
        # one the postcode index uses. A prefix search can then read the index
        # in order and stop after ``limit`` rows instead of sorting every match.
        sql = (
            f"SELECT {cols}\nFROM {PROPERTIES_TABLE}\n"
            f"WHERE {where}\n"
            f"ORDER BY postcode_clean USING ~<~, address_line_1, uprn\n"
            f"LIMIT %s"
        )
        return sql, [value, fetch]

    if search.mode == "postcode_and_text":
        # A full postcode is at most a few hundred rows, so take them first and
        # rank them by similarity to the rest of the query. Without
        # MATERIALIZED the planner also scans the trigram index for the words
        # (357k rows for 'FLAT 2 LONDON ROAD', ~250ms on 41M rows) just to AND
        # it with the postcode. Ranking instead of filtering also means a typo
        # or 'RD' vs 'ROAD' still puts the right address near the top.
        sql = (
            f"WITH in_postcode AS MATERIALIZED (\n"
            f"    SELECT {cols}, search_text\n"
            f"    FROM {PROPERTIES_TABLE}\n"
            f"    WHERE postcode_clean = %s\n"
            f")\n"
            f"SELECT {cols}\n"
            f"FROM in_postcode\n"
            f"ORDER BY similarity(search_text, %s) DESC, address_line_1, uprn\n"
            f"LIMIT %s"
        )
        return sql, [search.postcode_exact, search.text, fetch]

    if search.mode == "text":
        return _build_text_search(search, fetch)

    raise ValueError(f"unknown search mode {search.mode!r}")


def _build_text_search(
    search: ClassifiedSearch, fetch: int
) -> tuple[str, list[Any]]:
    """Free-text search on the trigram index (Phase 1).

    Every token must appear somewhere in ``search_text``. The inner query takes
    at most ``TEXT_CANDIDATE_LIMIT`` matches, unordered so it can stop early;
    only those are ranked by trigram similarity to the whole query.
    """
    likes, like_params = _like_clauses(search.tokens)
    cols = ", ".join(PROPERTIES_COLUMNS)
    sql = (
        f"SELECT {cols}\n"
        f"FROM (\n"
        f"    SELECT {cols}, search_text\n"
        f"    FROM {PROPERTIES_TABLE}\n"
        f"    WHERE {' AND '.join(likes)}\n"
        f"    LIMIT %s\n"
        f") AS candidates\n"
        f"ORDER BY similarity(search_text, %s) DESC, uprn\n"
        f"LIMIT %s"
    )
    return sql, [*like_params, TEXT_CANDIDATE_LIMIT, search.text, fetch]


# --------------------------------------------------------------------------- #
# History (one UPRN's sales and EPC certificates)                             #
# --------------------------------------------------------------------------- #
# ``GET /properties/{uprn}/history`` backs the expandable timeline under a
# property row. Two indexed lookups, newest first:
#
#   sales  property_uprn_mapping (uprn idx) -> land_registry_sales (PK)
#   epc    epc_domestic_certificates (uprn idx)
#
# ``uprn`` is text in both source tables, so it is bound as a string. Comparing
# against an integer would make Postgres cast the column and skip the index.
#
# No row cap: the timeline must show every sale and every certificate. The
# largest locally is one building-level UPRN with 369 linked sales.

SALE_HISTORY_COLUMNS: list[str] = [
    "transaction_id",
    "transfer_date",
    "price",
    "property_type",
    "old_new",
    "duration",
    "saon",
    "paon",
    "street",
    "locality",
    "town_city",
    "postcode",
    "ppd_category",
]

EPC_HISTORY_COLUMNS: list[str] = [
    "certificate_number",
    "lodgement_date",
    "inspection_date",
    "current_energy_rating",
    "potential_energy_rating",
    "current_energy_efficiency",
    "potential_energy_efficiency",
    "property_type",
    "built_form",
    "total_floor_area",
    "construction_age_band",
    "tenure",
    "transaction_type",
    "co2_emissions_current",
    "address1",
    "address2",
    "address3",
    "postcode",
]


def _check_uprn(uprn: int) -> str:
    if uprn < 0:
        raise ValueError(f"uprn must be non-negative, got {uprn}")
    return str(uprn)


def build_sales_history_query(uprn: int) -> tuple[str, list[Any]]:
    """SQL + params for every Land Registry sale linked to ``uprn``, newest first.

    Adds the match decision (``match_type`` / ``match_score``) so the UI can
    flag sales attached by fuzzy matching.
    """
    cols = ", ".join(f"s.{c}" for c in SALE_HISTORY_COLUMNS)
    sql = (
        f"SELECT {cols}, m.match_type, m.match_score\n"
        f"FROM {UPRN_MAPPING_TABLE} AS m\n"
        f"JOIN {LAND_REGISTRY_TABLE} AS s ON s.transaction_id = m.transaction_id\n"
        f"WHERE m.uprn = %s AND m.transaction_id IS NOT NULL\n"
        f"ORDER BY s.transfer_date DESC NULLS LAST, s.transaction_id"
    )
    return sql, [_check_uprn(uprn)]


def build_epc_history_query(uprn: int) -> tuple[str, list[Any]]:
    """SQL + params for every EPC certificate lodged for ``uprn``, newest first."""
    sql = (
        f"SELECT {', '.join(EPC_HISTORY_COLUMNS)}\n"
        f"FROM {EPC_TABLE}\n"
        f"WHERE uprn = %s\n"
        f"ORDER BY lodgement_date DESC NULLS LAST, certificate_number DESC"
    )
    return sql, [_check_uprn(uprn)]
