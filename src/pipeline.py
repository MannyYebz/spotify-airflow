"""Task entry points. Only small S3 object references leave these functions."""

import argparse
import hashlib
import logging

from dotenv import load_dotenv

from src.config import Settings
from src.extract.raw import DATASETS, extract_dataset
from src.load.s3 import S3Storage
from src.spotify import SpotifyClient
from src.transform.normalize import normalize
from src.validation import ValidationError, utc_timestamp


def object_keys(
    settings: Settings, dataset: str, run_id: str, end: str
) -> tuple[str, str]:
    if dataset not in DATASETS or not run_id:
        raise ValidationError("Dataset and run_id are required")
    date = utc_timestamp(end).date().isoformat()
    run = hashlib.sha256(run_id.encode()).hexdigest()
    partition = f"{dataset}/date={date}/run={run}"
    prefix = f"{settings.prefix}/" if settings.prefix else ""
    return (
        f"{prefix}raw/{partition}/response.json",
        f"{prefix}processed/{partition}/part-00000.parquet",
    )


def extract_to_s3(dataset: str, start: str, end: str, run_id: str) -> dict:
    start_dt, end_dt = utc_timestamp(start), utc_timestamp(end)
    if start_dt >= end_dt:
        raise ValidationError("Interval start must be before end")
    settings = Settings.from_env(require_s3=True)
    raw_key, processed_key = object_keys(settings, dataset, run_id, end)
    storage = S3Storage(settings)
    existing = storage.read_json(raw_key)
    if existing is None:
        raw = extract_dataset(SpotifyClient(settings), dataset, start, end)
        storage.write_raw(raw_key, raw)
    else:
        if (
            existing.get("dataset") != dataset
            or utc_timestamp(existing.get("interval_start")) != start_dt
            or utc_timestamp(existing.get("interval_end")) != end_dt
        ):
            raise ValidationError(
                "Run ID already exists with a different interval or dataset"
            )
        logging.getLogger(__name__).info("Reusing raw extraction key=%s", raw_key)
    return {"raw_key": raw_key, "processed_key": processed_key}


def process_to_s3(reference: dict) -> dict:
    storage = S3Storage(Settings.from_env(require_s3=True, require_spotify=False))
    raw = storage.read_json(reference["raw_key"])
    if raw is None:
        raise FileNotFoundError("Raw S3 object is missing")
    table = normalize(raw)
    storage.write_parquet(reference["processed_key"], table)
    return {"key": reference["processed_key"], "rows": table.num_rows}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a Spotify extraction interval without Airflow"
    )
    parser.add_argument(
        "--start", required=True, help="Inclusive ISO timestamp with timezone"
    )
    parser.add_argument(
        "--end", required=True, help="Exclusive ISO timestamp with timezone"
    )
    parser.add_argument(
        "--run-id", required=True, help="Reuse this ID to retry the same interval"
    )
    args = parser.parse_args()
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    for dataset in DATASETS:
        process_to_s3(extract_to_s3(dataset, args.start, args.end, args.run_id))


if __name__ == "__main__":
    main()
