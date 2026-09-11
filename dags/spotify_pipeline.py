"""A single account, with ETL and storage implemented in the src package."""

import os
from datetime import timedelta

import pendulum
from airflow.decorators import dag, task

from src.extract.raw import DATASETS
from src.pipeline import extract_to_s3, process_to_s3


@dag(
    dag_id="spotify_pipeline",
    schedule=os.getenv("SPOTIFY_SCHEDULE", "*/15 * * * *"),
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=1,  # Serialize token refreshes for this single-account cache.
    default_args={
        "owner": "data-engineering",
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(minutes=30),
        "execution_timeout": timedelta(minutes=20),
    },
    tags=["spotify", "s3"],
)
def spotify_pipeline():
    @task
    def extract(dataset, data_interval_start=None, data_interval_end=None, run_id=None):
        return extract_to_s3(
            dataset,
            data_interval_start.isoformat(),
            data_interval_end.isoformat(),
            run_id,
        )

    @task
    def process(reference):
        return process_to_s3(reference)

    for dataset in DATASETS:
        process.override(task_id=f"process_{dataset}")(
            extract.override(task_id=f"extract_{dataset}")(dataset)
        )


spotify_pipeline()
