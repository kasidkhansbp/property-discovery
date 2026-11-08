"""Connections the land_registry assets need: R2 (object storage) and Postgres.

Kept as Dagster resources so assets don't hard-code credentials and so they can
be swapped for fakes in tests. Credentials come from the environment (see
`__init__.py`), never from the code or the repo.
"""

from __future__ import annotations

from typing import IO

import boto3
import dagster as dg
import psycopg
from botocore.client import BaseClient
from botocore.config import Config


class R2Resource(dg.ConfigurableResource):
    """Cloudflare R2 (S3-compatible) — the raw + clean object store.

    Serves two consumers:
      * boto3, for streaming the raw download straight into the bucket, and
      * DuckDB (httpfs), for reading/writing objects directly over S3 so no
        data ever has to touch the local filesystem.
    """

    bucket: str
    endpoint_url: str  # e.g. https://<account-id>.r2.cloudflarestorage.com
    access_key_id: str
    secret_access_key: str
    region: str = "auto"  # R2 ignores region but the S3 clients require one

    def get_client(self) -> BaseClient:
        """A boto3 S3 client pointed at R2."""
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name=self.region,
            # R2 wants path-style addressing and the s3v4 signature.
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def upload_stream(self, fileobj: IO[bytes], key: str) -> None:
        """Stream a file-like object into the bucket.

        Uses boto3's managed multipart upload, so a multi-GB source is sent in
        chunks — it never has to fit in memory or land on local disk.
        """
        self.get_client().upload_fileobj(fileobj, self.bucket, key)

    def object_size(self, key: str) -> int:
        """Bytes stored at `key` (handy for logging after an upload)."""
        head = self.get_client().head_object(Bucket=self.bucket, Key=key)
        return int(head["ContentLength"])

    def s3_url(self, key: str) -> str:
        """The `s3://bucket/key` URL DuckDB uses to read/write the object."""
        return f"s3://{self.bucket}/{key}"

    def configure_duckdb(self, con) -> None:
        """Point a DuckDB connection at this R2 bucket over httpfs.

        After this call, DuckDB can `read_csv`/`read_parquet`/`COPY ... TO` any
        `s3_url(key)` directly, with no local staging files.
        """
        host = self.endpoint_url.split("://", 1)[-1].rstrip("/")
        con.execute("INSTALL httpfs; LOAD httpfs;")
        con.execute(f"SET s3_region = '{self.region}';")
        con.execute(f"SET s3_endpoint = '{host}';")
        con.execute(f"SET s3_access_key_id = '{self.access_key_id}';")
        con.execute(f"SET s3_secret_access_key = '{self.secret_access_key}';")
        con.execute("SET s3_url_style = 'path';")
        con.execute("SET s3_use_ssl = true;")


class PostgresResource(dg.ConfigurableResource):
    """Postgres + PostGIS — the serving database."""

    dsn: str  # e.g. postgresql://user:pass@host:5432/dbname

    def connect(self) -> psycopg.Connection:
        """A psycopg (v3) connection. Caller manages the transaction/commit."""
        return psycopg.connect(self.dsn)
