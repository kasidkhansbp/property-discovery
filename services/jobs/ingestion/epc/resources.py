"""Connections the epc assets need: R2 (object storage), Postgres, and the EPC
Open Data Communities API credential.

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
      * boto3, for streaming the raw download straight into the bucket (and
        pulling it back when the raw object is a ZIP that must be extracted), and
      * DuckDB (httpfs), for reading/writing objects directly over S3 so no
        clean/load data ever has to touch the local filesystem.
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

    def download_file(self, key: str, dest: str) -> None:
        """Download the object at `key` to a local path `dest`.

        The counterpart to `upload_stream`: EPC's raw object is a ZIP of many
        per-local-authority CSVs, which DuckDB can't read in place over httpfs,
        so the clean step pulls it back to a temp file to extract it.
        """
        self.get_client().download_file(self.bucket, key, dest)

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


class EpcResource(dg.ConfigurableResource):
    """The MHCLG "Get energy performance of buildings data" API credential.

    The new service (get-energy-performance-data.communities.gov.uk, which
    replaced the retired Open Data Communities site) gates the bulk download
    behind a **bearer token** rather than the old HTTP Basic email:api-key.
    The token is issued via GOV.UK One Login and shown on your "my account"
    page once signed in. We keep just the token here so the credential never
    lands in code or the repo.
    """

    auth_token: str  # GOV.UK One Login bearer token (from the "my account" page)

    def auth_headers(self) -> dict[str, str]:
        """The headers the EPC download endpoint requires.

        The bulk endpoint answers with a 302 to a presigned S3 URL; ``Accept``
        is ``application/json`` (the service negotiates on that), and the
        bearer token authorises the initial request. ``requests`` drops the
        Authorization header on the cross-host redirect to S3, which is exactly
        what the presigned URL expects.
        """
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Accept": "application/json",
        }
