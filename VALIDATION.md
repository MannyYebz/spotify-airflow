# Validation record

Checked on 2026-09-11. All changes are confined to this repository copy. Existing
local `.env`, token cache, and generated personal data were not overwritten.

## Executed checks

| Check | Result |
| --- | --- |
| Locked local environment, Python 3.12.3 | `uv sync --frozen --extra reports` succeeded |
| Local pytest suite | **115 passed, 1 skipped**; only the Airflow-specific test skipped |
| Airflow-constrained environment, Python 3.12.3 / Airflow 2.11.2 | **116 passed**, with two upstream Airflow deprecation warnings |
| DAG parsing | DagBag loaded `spotify_pipeline` without import errors; six tasks and all three extract/process dependencies checked |
| DAG execution smoke test | `dag.test()` completed all six tasks using a temporary SQLite metadata DB, mocked Spotify client, and in-memory storage; three raw objects and three Parquet round trips |
| Airflow initialization | Metadata migration and admin creation ran twice against temporary SQLite; exactly one test admin remained |
| Imports | All 17 `src` modules plus `main` imported with the optional report dependencies; no Spotify/AWS calls |
| Syntax | `compileall` on `src`, `dags`, `scripts`, and `main.py` succeeded |
| Style | `ruff check .`, `ruff format --check .`, and `git diff --check` succeeded |
| Compose | `docker compose --env-file /tmp/spotify-compose-validation.env config --quiet` succeeded using dummy values for required interpolation variables |
| Airflow deployment dependencies | Installed successfully using the official 2.11.2/Python 3.12 constraints; Pandas 2.1.4 and PyArrow 22.0.0 tested |
| Ignore rules | Confirmed local environment, tokens, AWS files, generated data, logs, and volume directories are ignored |

The lightweight `uv.lock` environment uses Pandas 2.3.3 and PyArrow 19.0.1, so tests
also exercise a second compatible dependency combination. The Docker image uses
the official Airflow constraints rather than this development lockfile.

The DAG smoke test exercises orchestration and task handoffs, not a live Spotify
account, S3 service, LocalExecutor worker pool, or PostgreSQL server. Credentials
and remote storage are mocked in the test suite.

## Credential scan finding

Scanned the current tracked/unignored source files and 45 historical Git blobs,
checking common AWS/GitHub/private-key/JWT patterns and exact matches against the
local configured secrets without printing their values.

- **Current source:** no detected secret matches. `.env` and `.token_cache.json`
  are untracked and ignored; the Docker context uses an allowlist.
- **Inherited Git history:** commit `8870de2` contains `.token_cache.json` with a
  refresh token that matches the current local cache. Commit `4c09b8a` removed
  the file from tracking but did not erase it from history.

Revoke that Spotify authorization and bootstrap new tokens before sharing the
repository. GitHub publication uses a fresh initial commit, excluding the inherited history.
The source copy's previous Git metadata was retained in a private local backup.
The scan is a targeted check, not a guarantee that every possible secret format
was detected. No credential values are included in this report.

## Not validated

Docker Desktop was unavailable after the host shutdown. Its start command returned,
but the daemon still could not be reached. Consequently the Docker image build,
container startup, PostgreSQL-backed migrations, scheduler health checks, and
live S3/Spotify execution **were not validated**. Compose syntax and the image's
Python dependency set were checked independently as described above.

After Docker is available and `.env` is configured, run the README's build,
initialization, OAuth, and startup commands. Check `docker compose ps`, Airflow
import errors, task logs, and the resulting S3 objects. The committed source is
ready for those environment-dependent checks; this record does not claim a live
end-to-end deployment.
