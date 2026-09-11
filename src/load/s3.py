"""S3 JSON and Parquet I/O using AWS's normal credential provider chain."""

import json
import logging

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.config import Config
from botocore.exceptions import ClientError

from src.config import Settings
from src.validation import ValidationError

log = logging.getLogger(__name__)


class S3Storage:
    def __init__(self, settings: Settings, client=None):
        self.bucket = settings.bucket
        self.client = client or boto3.client(
            "s3",
            region_name=settings.region,
            config=Config(
                retries={"mode": "standard", "total_max_attempts": 4},
                connect_timeout=10,
                read_timeout=60,
            ),
        )

    def read_json(self, key: str) -> dict | None:
        try:
            result = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] in {"NoSuchKey", "404"}:
                return None
            raise
        body = result["Body"]
        try:
            value = json.loads(body.read())
        finally:
            body.close()
        if not isinstance(value, dict):
            raise ValidationError("Stored JSON must be an object")
        return value

    def write_raw(self, key: str, data: dict) -> None:
        """First complete extraction wins, including concurrent/retried writes."""
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=json.dumps(data, ensure_ascii=False, allow_nan=False).encode(),
                ContentType="application/json",
                ServerSideEncryption="AES256",
                IfNoneMatch="*",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] != "PreconditionFailed":
                raise
        log.info("Raw object ready key=%s", key)

    def write_parquet(self, key: str, table: pa.Table) -> None:
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression="snappy", version="2.6")
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=sink.getvalue().to_pybytes(),
            ContentType="application/vnd.apache.parquet",
            ServerSideEncryption="AES256",
        )
        log.info("Wrote Parquet key=%s rows=%s", key, table.num_rows)
