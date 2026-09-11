import io
import json
from unittest.mock import Mock

import boto3
import pyarrow.parquet as pq
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from src import pipeline
from src.load.s3 import S3Storage
from src.transform.normalize import normalize


def test_raw_json_s3_parameters(settings, raw):
    client = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    with Stubber(client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "test-bucket",
                "Key": "raw/test.json",
                "Body": json.dumps(raw, ensure_ascii=False, allow_nan=False).encode(),
                "ContentType": "application/json",
                "ServerSideEncryption": "AES256",
                "IfNoneMatch": "*",
            },
        )
        S3Storage(settings, client).write_raw("raw/test.json", raw)
        stub.assert_no_pending_responses()


def test_read_json_closes_body(settings, raw):
    client, body = Mock(), io.BytesIO(json.dumps(raw).encode())
    client.get_object.return_value = {"Body": body}
    assert S3Storage(settings, client).read_json("key") == raw
    assert body.closed


@pytest.mark.parametrize("code", ["AccessDenied", "SlowDown", "NoSuchBucket"])
def test_s3_failures_are_not_swallowed(settings, code):
    client = Mock()
    client.get_object.side_effect = ClientError({"Error": {"Code": code}}, "GetObject")
    with pytest.raises(ClientError):
        S3Storage(settings, client).read_json("key")


def test_missing_object(settings):
    client = Mock()
    client.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey"}}, "GetObject"
    )
    assert S3Storage(settings, client).read_json("key") is None


def test_raw_conflict_keeps_original(settings, raw):
    client = Mock()
    client.put_object.side_effect = ClientError(
        {"Error": {"Code": "PreconditionFailed"}}, "PutObject"
    )
    S3Storage(settings, client).write_raw("key", raw)
    client.put_object.side_effect = ClientError(
        {"Error": {"Code": "SlowDown"}}, "PutObject"
    )
    with pytest.raises(ClientError):
        S3Storage(settings, client).write_raw("key", raw)


@pytest.mark.parametrize("empty", [False, True])
def test_parquet_round_trip(settings, raw, empty):
    if empty:
        raw["pages"][0]["items"] = []
    table = normalize(raw)
    client = Mock()
    S3Storage(settings, client).write_parquet("processed/test.parquet", table)
    args = client.put_object.call_args.kwargs
    restored = pq.ParquetFile(io.BytesIO(args["Body"])).read()
    assert restored.equals(table)
    assert args["ServerSideEncryption"] == "AES256"


def test_paths_deterministic_and_safe(settings):
    first = pipeline.object_keys(
        settings, "recently_played", "scheduled__/../../id", "2026-09-01T00:00:00Z"
    )
    assert first == pipeline.object_keys(
        settings, "recently_played", "scheduled__/../../id", "2026-09-01T00:00:00Z"
    )
    assert ".." not in first[0] and "date=2026-09-01" in first[0]
    assert first != pipeline.object_keys(
        settings, "recently_played", "other", "2026-09-01T00:00:00Z"
    )


def test_pipeline_retry_reuses_raw_and_reprocesses(settings, raw, monkeypatch):
    storage, client = Mock(), Mock()
    monkeypatch.setattr(pipeline.Settings, "from_env", lambda **_: settings)
    monkeypatch.setattr(pipeline, "S3Storage", lambda _: storage)
    monkeypatch.setattr(pipeline, "SpotifyClient", client)
    storage.read_json.return_value = raw
    reference = pipeline.extract_to_s3(
        "recently_played", raw["interval_start"], raw["interval_end"], "run"
    )
    client.assert_not_called()
    storage.write_raw.assert_not_called()
    result = pipeline.process_to_s3(reference)
    assert result["rows"] == 1
    storage.write_parquet.assert_called_once()


def test_pipeline_extract_then_process(settings, raw, monkeypatch):
    storage, extract = Mock(), Mock(return_value=raw)
    monkeypatch.setattr(pipeline.Settings, "from_env", lambda **_: settings)
    monkeypatch.setattr(pipeline, "S3Storage", lambda _: storage)
    monkeypatch.setattr(pipeline, "SpotifyClient", Mock())
    monkeypatch.setattr(pipeline, "extract_dataset", extract)
    storage.read_json.side_effect = [None, raw]
    reference = pipeline.extract_to_s3(
        "recently_played", raw["interval_start"], raw["interval_end"], "run"
    )
    assert set(reference) == {"raw_key", "processed_key"}
    storage.write_raw.assert_called_once_with(reference["raw_key"], raw)
    assert pipeline.process_to_s3(reference)["rows"] == 1


def test_missing_raw_prevents_processed_write(settings, monkeypatch):
    storage = Mock()
    storage.read_json.return_value = None
    monkeypatch.setattr(pipeline.Settings, "from_env", lambda **_: settings)
    monkeypatch.setattr(pipeline, "S3Storage", lambda _: storage)
    with pytest.raises(FileNotFoundError):
        pipeline.process_to_s3({"raw_key": "raw", "processed_key": "processed"})
    storage.write_parquet.assert_not_called()


def test_reused_run_id_rejects_changed_interval(settings, raw, monkeypatch):
    storage = Mock()
    storage.read_json.return_value = raw
    monkeypatch.setattr(pipeline.Settings, "from_env", lambda **_: settings)
    monkeypatch.setattr(pipeline, "S3Storage", lambda _: storage)
    with pytest.raises(ValueError, match="different interval"):
        pipeline.extract_to_s3(
            "recently_played", "2026-08-01T00:00:00Z", raw["interval_end"], "run"
        )
    storage.write_raw.assert_not_called()


def test_bad_stored_json_closes_body(settings):
    client, body = Mock(), io.BytesIO(b"not json")
    client.get_object.return_value = {"Body": body}
    with pytest.raises(ValueError):
        S3Storage(settings, client).read_json("key")
    assert body.closed
