"""API gateway layer — the thin HTTP surface over the serving database.

The ingestion services (``services/ingestion/*``) build and populate the tables;
this package only *reads* them and exposes them over HTTP for the frontend. It
owns no business logic of its own and holds no second copy of the schema — the
column names it filters, sorts, and returns are imported from the owning
service's schema module so the two can never drift apart.
"""
