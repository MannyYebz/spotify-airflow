# Pipeline design decisions

The original project was a local report with cached OAuth, single-page Spotify
requests, a cumulative CSV history, and charts. Airflow and S3 existed only as
plans; the DAG/test/load directories were empty and Docker did not build.

The working report and extended-history importer remain. Their extraction adapters
now use the shared client, and their output remains local. The scheduled pipeline
publishes three separate S3 datasets rather than coupling charts to task execution.

- **LocalExecutor and PostgreSQL:** sufficient for one account. No broker is needed.
  Tasks are serial to keep token rotation safe with a shared cache. Do not increase
  concurrency without revisiting token coordination.
- **Raw before processed:** original pages and request metadata make malformed
  responses inspectable and allow transformation changes without another API call.
  Page-level protocol failures abort before storage; nested-record failures leave
  the complete raw extraction available.
- **Explicit Arrow schemas:** stable empty/nonempty tables, typed UTC timestamps,
  nullable measurements, and list fields without relying on dtype inference.
- **Interval events versus snapshots:** recent plays are filtered into UTC intervals;
  top items are snapshots of current affinity. Their `extracted_at` must not be
  interpreted as a historical ranking for the interval.
- **Deterministic objects:** retrying a run reuses raw and overwrites its processed
  object. Distinct overlapping runs are retained independently; consumers deduplicate
  events by `event_id`. No read/merge/write of a shared daily object is required.
- **Fail malformed data:** no silent empty batches for API protocol errors. Null or
  unavailable tracks are a documented exception with counts in task logs.
- **Separate dependency sets:** `uv.lock` supports lightweight Python development;
  Airflow uses its official constraints via `requirements-airflow.txt` on Python 3.12.

Useful future work includes raw-envelope migrations, compaction, data quality
metrics/alerting, export-to-S3 ingestion, and recovery for delayed events. These
should be driven by observed needs rather than adding services in advance.

Setup and operational semantics live in README.md. Actual verification results
and untested deployment boundaries live in VALIDATION.md.
