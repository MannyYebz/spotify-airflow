# Spotify Airflow pipeline

A single-account data pipeline that captures Spotify listening events and top-item
snapshots, preserves the API responses in S3, and publishes typed Parquet tables.
Airflow owns scheduling and retries; ordinary Python modules own extraction,
validation, transformation, and storage. PostgreSQL stores Airflow metadata.

The original local CSV archive, extended-history importer, and chart report remain
available as an optional workflow. Neither workflow depends on another repository.

## Architecture

```text
Spotify OAuth + Web API
          |
Airflow scheduler (LocalExecutor) ---- PostgreSQL metadata
          |
          +-- extract_recently_played --> S3 raw JSON --> process_recently_played
          +-- extract_top_tracks ------> S3 raw JSON --> process_top_tracks
          +-- extract_top_artists -----> S3 raw JSON --> process_top_artists
                                                               |
                                                        S3 Parquet tables
```

Each extract/process pair is a separate task chain. Only S3 keys and row counts
pass through XCom. Tasks execute serially (`max_active_tasks=1`) to avoid concurrent
refreshes of the single account's token cache. There is one active DAG run at a
time. LocalExecutor needs no Redis or separate worker service.

## Setup

Requirements: Python 3.12 or 3.13 for local ETL, `uv`, a Spotify developer app,
and an existing private S3 bucket. Docker deployment uses Python 3.12, Airflow
2.11.2, PostgreSQL 16, and Docker Compose v2 or newer.

```bash
uv sync --frozen
cp .env.example .env   # fresh clone only; preserve an existing .env
```

Fill the relevant values in `.env`. It is ignored by Git and excluded from the
Docker build context. CLI entry points load `.env`; library functions and DAG
imports do not. Airflow receives configuration from Compose's environment.

### Spotify authorization

Register the exact redirect URI in your Spotify app, for example
`http://127.0.0.1:9090`. Enable access for your account as required by the app's
Spotify quota mode. The scopes are `user-top-read`, `user-read-recently-played`,
and `user-read-private` (the last supports the retained profile report).

```bash
uv run --frozen python -m src.auth
```

Open the printed authorization URL, approve access, and paste the entire redirect
URL. No local callback server is required; the destination page may fail to load.
The command verifies the redirect and OAuth state, exchanges the code, and saves
`.token_cache.json` with mode 0600. Access tokens refresh before expiration; a
rotated refresh token is saved atomically. Tokens are never printed.

Scheduled tasks never prompt for authorization. Bootstrap their **container token
volume** separately using the command below, or supply `SPOTIFY_REFRESH_TOKEN`.
The local `.token_cache.json` is not copied into Docker. Do not run the local CLI
and scheduler concurrently against the same Spotify authorization. If authorization
is revoked or a cache is corrupt, stop collection and repeat the OAuth bootstrap.

### S3 access

The bucket must already exist. Boto3 uses its normal credential chain: local AWS
profiles, environment credentials, or an attached IAM role. In Compose, environment
credentials in `.env` are available to tasks; host `~/.aws` profiles are not mounted.
Temporary credentials require `AWS_SESSION_TOKEN`. Omit empty AWS key variables
when using an IAM role.

Grant `s3:GetObject` and `s3:PutObject` on the selected prefix, plus `s3:ListBucket`
on the bucket restricted to that prefix. List permission allows missing keys to
return 404 instead of AccessDenied. The code explicitly requests SSE-S3 (`AES256`);
buckets that mandate a particular KMS key need a storage change and KMS permissions.
No bucket creation or public access is performed.

## Configuration

| Variable | Required / default |
| --- | --- |
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` | Required for OAuth and extraction |
| `SPOTIFY_REDIRECT_URI` | `http://127.0.0.1:9090`; must match app registration |
| `SPOTIFY_REFRESH_TOKEN` | Optional bootstrap when no cached refresh token exists |
| `SPOTIFY_TOKEN_CACHE` | `.token_cache.json` locally; Compose overrides to its token volume |
| `S3_BUCKET` | Required for S3 tasks; bucket name without `s3://` |
| `S3_PREFIX` | `spotify`; use a separate prefix for each account |
| `AWS_DEFAULT_REGION` | `us-east-1` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Only when using environment AWS credentials |
| `SPOTIFY_TIME_RANGE` | `medium_term`; also `short_term` or `long_term` |
| `SPOTIFY_TOP_LIMIT` | `50`; total requested top items, 1–1000, pages of at most 50 |
| `SPOTIFY_MAX_PAGES` | `100`; exceeding it fails rather than silently truncating |
| `SPOTIFY_SCHEDULE` | `*/15 * * * *` (UTC cron; read when the DAG is parsed) |
| `HTTP_ATTEMPTS` | `4`, including the first request; allowed 1–10 |
| `HTTP_TIMEOUT` | `30` seconds per HTTP request |
| `HTTP_MAX_RETRY_WAIT` | `120` seconds per local retry delay |
| `POSTGRES_PASSWORD` | Required by Compose; use a generated hex value safe in a URL |
| `AIRFLOW_FERNET_KEY` | Required by Compose; valid Fernet key |
| `AIRFLOW_WEBSERVER_SECRET_KEY` | Required by Compose; shared webserver/scheduler secret |
| `AIRFLOW_ADMIN_USER` | `admin` |
| `AIRFLOW_ADMIN_EMAIL`, `AIRFLOW_ADMIN_PASSWORD` | Required by Compose initialization |

The processing function needs S3 configuration only; it can reprocess a captured
raw object without Spotify credentials. Configuration is validated on task execution.

## Docker and Airflow

Set all required Compose variables in `.env`. Generate separate random hex values
for `POSTGRES_PASSWORD`, `AIRFLOW_WEBSERVER_SECRET_KEY`, and
`AIRFLOW_ADMIN_PASSWORD`; save them privately:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
# Generate AIRFLOW_FERNET_KEY (URL-safe base64 of 32 random bytes):
python3 -c 'import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'

docker compose config --quiet
docker compose build
docker compose run --rm airflow-init
# Bootstrap OAuth into the persistent container volume:
docker compose run --rm --no-deps airflow-scheduler python -m src.auth
docker compose up -d
```

Open `http://localhost:8080` and sign in with the configured admin account. New
DAGs start paused. After authentication and S3 permissions are ready:

```bash
docker compose exec airflow-scheduler airflow dags list-import-errors
docker compose exec airflow-scheduler airflow dags unpause spotify_pipeline
docker compose exec airflow-scheduler airflow dags trigger spotify_pipeline
docker compose logs -f airflow-scheduler
docker compose ps
```

The default schedule captures 15-minute intervals with `catchup=False`. A manual
trigger uses Airflow's inferred data interval, so it can overlap an existing run.
Each task retries three times, with exponential delays from five minutes capped at
30 minutes, and a 20-minute execution timeout. Logs contain dataset names, counts,
S3 keys, and retry delays. The webserver is bound to localhost; PostgreSQL is only
reachable inside the Compose network. Named volumes persist logs, metadata, and
tokens. `docker compose down` preserves them. Adding `--volumes` deletes that state,
including the authorization cache.

Initialization migrates metadata and creates the admin only when absent. Changing
`AIRFLOW_ADMIN_PASSWORD` later does not reset an existing user; use Airflow's user
management. Changing the database password does not update an existing Postgres
volume. Rebuild and recreate containers after source or configuration changes.

The Docker image installs `requirements-airflow.txt` using Airflow's official
Python 3.12 constraints; local ETL uses `uv.lock`. This avoids installing the full
orchestrator for ordinary transformation or API development.

## Data and S3 layout

```text
s3://<bucket>/<prefix>/
  raw/<dataset>/date=YYYY-MM-DD/run=<sha256-run-id>/response.json
  processed/<dataset>/date=YYYY-MM-DD/run=<sha256-run-id>/part-00000.parquet
```

`<dataset>` is `recently_played`, `top_tracks`, or `top_artists`. `date` is the UTC
**interval end date**, not necessarily the play date. The run identifier is hashed
for safe, stable paths. Raw JSON includes the complete fetched pages, schema
version, extraction time, requested interval, and ranking settings.

1. Extraction authenticates, follows `next` URLs, and validates page structure.
2. A complete extraction is conditionally written to raw S3 (`IfNoneMatch: *`).
3. Processing reads raw JSON, validates and normalizes it into an explicit Arrow
   schema, deduplicates it, and writes Snappy-compressed Parquet.
4. A retry reuses an existing raw object and overwrites the same processed key.
   A conflicting interval under the same run ID is rejected. Clearing a process
   task reruns transformation without a Spotify request.

Raw pages are retained unmodified inside the envelope. Top-item requests may fetch
one page beyond the requested item count; transformation takes the requested count.
Partial extractions are not published. There is no multi-dataset transaction: one
chain can finish while another fails, and Airflow exposes that state.

### Table semantics

- **Recent plays:** one event per `(track_id, played_at_utc)` within the inclusive
  start/exclusive end interval. UTC-normalized timestamps feed a stable SHA-256
  `event_id`. Repeat listens at different times remain distinct. Optional fields
  include name, album, artist ID/name arrays, and full track duration.
  `ms_played` stays null because this API does not report actual time listened.
- **Top tracks/artists:** observations at `extracted_at`, with Spotify's ranking
  and `time_range`. Duplicate IDs keep their first original rank, so rank gaps
  are possible. Artist genres are arrays. These are affinity snapshots, not play
  counts or reconstructions of a historical interval.
- **All tables:** explicit typed schemas, including empty batches; UTC microsecond
  timestamps; nullable optional metadata; nonnegative integer durations.
  Unknown extra API fields stay in raw JSON and are ignored by normalization.
- Null/unavailable/local tracks without a stable ID are counted in logs and skipped.
  Malformed page structures, required timestamps, or nested types fail processing
  instead of silently turning a broken response into an empty successful dataset.
  Raw JSON remains available for investigation.

Normal scheduled intervals do not overlap. Separate manual runs or changed
schedules can overlap: deduplicate recent-play reads on `event_id` across files
when combining those runs. This project does not compact or upsert an entire data
lake. Each account requires its own prefix; event IDs do not encode account identity.

## Local execution and reprocessing

After local OAuth and AWS setup, run a recent interval explicitly:

```bash
uv run --frozen python -m src.pipeline \
  --start 2026-09-11T12:00:00Z --end 2026-09-11T12:15:00Z \
  --run-id local-20260911T1200
```

Replace these timestamps with an interval Spotify can still return. Reuse the same
run ID and interval to retry. To reprocess an existing raw object without extracting:

```python
from dotenv import load_dotenv
from src.pipeline import process_to_s3

load_dotenv()
process_to_s3(
    {
        "raw_key": "spotify/raw/recently_played/date=.../run=.../response.json",
        "processed_key": "spotify/processed/recently_played/date=.../run=.../part-00000.parquet",
    }
)
```

The optional original report runs locally:

```bash
uv sync --frozen --extra reports
uv run --frozen --extra reports python main.py
```

It writes CSVs and PNGs below `data/recent_history/` and
`data/analytics_history/`. Optional Spotify exports go in
`data/Spotify Extended Streaming History/Streaming_History_*.json`.
Actual `ms_played` from exports enriches matching archived API events. Charts use
America/New_York for display while stored timestamps remain UTC. The Airflow image
omits desktop plotting dependencies and does not import this local archive into S3.

## Tests and checks

```bash
uv sync --frozen
uv run --frozen pytest -q
uv run --frozen pytest --cov=src --cov-report=term-missing
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen python -m compileall -q src dags scripts main.py
docker compose config --quiet
```

Tests mock Spotify and AWS, block unexpected Requests calls, and use temporary
caches. They cover OAuth state/refresh, permanent and transient HTTP failures,
cursor/offset pagination, malformed data, UTC boundaries, deduplication, schema
stability, Parquet round trips, S3 errors, task handoffs, and local report regressions.
The DAG test skips when Airflow is absent. To run it and the full suite with the
same dependency constraints used by Docker, use an isolated Python 3.12 environment:

```bash
uv venv .venv-airflow --python 3.12
uv pip install --python .venv-airflow/bin/python -r requirements-airflow.txt pytest
AIRFLOW_HOME=/tmp/spotify-airflow-tests AIRFLOW__CORE__LOAD_EXAMPLES=false \
  .venv-airflow/bin/python -m pytest -q
```

See `VALIDATION.md` for the checks actually performed and their limits.

## Repository map

```text
dags/spotify_pipeline.py       Scheduling and task dependencies
src/auth.py                   OAuth bootstrap, cache, and refresh
src/config.py                 Environment configuration
src/http.py                   HTTP retry policy and JSON parsing
src/spotify.py                API client and pagination
src/validation.py             Shared validation primitives
src/extract/raw.py            Dataset extraction and raw envelopes
src/extract/fetch_data.py      Compatibility adapters for local reports
src/transform/normalize.py     Arrow schemas and transformations
src/transform/analytics_history.py  Existing local CSV/export archive
src/transform/analyze.py       Existing charts
src/load/s3.py                Raw JSON and Parquet storage
src/pipeline.py               Reusable task functions and CLI
src/utils/terminal.py         Local report presentation
scripts/init_airflow.py       Metadata migration and admin creation
tests/                        Mocked regression tests and DAG checks
main.py                       Optional original report
requirements-airflow.txt      Constrained Airflow deployment dependencies
pyproject.toml, uv.lock        Local package and development dependencies
Dockerfile, docker-compose.yml
.env.example
```

## Operational limits

Spotify's recent-play endpoint is not a full-history export. Frequent scheduling
reduces gaps but cannot guarantee complete history after downtime, delayed API
visibility, or high activity. Cursor pagination only retrieves what Spotify makes
available. Old Airflow intervals cannot reliably be backfilled from the API; use
retained raw responses for replay. Top-item responses always describe the current
account state, even during a historical run.

The pipeline buffers bounded pages and Parquet in memory, creates small per-run
files, and has no compaction job, catalog, alert delivery, or account multiplexing.
Use Airflow's task logs and failure status for diagnosis. A long `Retry-After`
exceeding the local wait budget raises a retryable error instead of retrying early;
Airflow may try again later and receive another 429. For production deployment,
review Airflow support/security updates, access controls, secret management, and
retention policies for personal listening data.

Protocol references: [Spotify authorization code flow](https://developer.spotify.com/documentation/web-api/tutorials/code-flow),
[recent plays](https://developer.spotify.com/documentation/web-api/reference/get-recently-played),
[top items](https://developer.spotify.com/documentation/web-api/reference/get-users-top-artists-and-tracks),
[rate limits](https://developer.spotify.com/documentation/web-api/concepts/rate-limits),
and [Airflow 2.11.2 Docker documentation](https://airflow.apache.org/docs/apache-airflow/2.11.2/howto/docker-compose/).

## License

The original code and documentation in this repository are licensed under the
[MIT License](LICENSE), copyright © 2026 MannyYebz.

Third-party dependencies retain their own licenses and required notices. The MIT
license does not grant rights to Spotify content, API responses, artwork, music,
trademarks, or other third-party material. Access to and use of Spotify's API and
data remain subject to the [Spotify Developer Terms](https://developer.spotify.com/terms)
and [Developer Policy](https://developer.spotify.com/policy). This project is not
affiliated with or endorsed by Spotify.

Licensing the code does not authorize indefinite retention or redistribution of
Spotify data. The pipeline currently has no enforced retention policy; operators
must address applicable storage and deletion requirements before live use.
