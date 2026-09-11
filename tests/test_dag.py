from pathlib import Path

import pytest


def test_dag_imports_and_dependencies():
    pytest.importorskip("airflow")
    from airflow.models import DagBag

    bag = DagBag(
        dag_folder=str(Path(__file__).parents[1] / "dags"), include_examples=False
    )
    assert not bag.import_errors
    dag = bag.dags["spotify_pipeline"]
    assert len(dag.tasks) == 6
    assert dag.catchup is False and dag.max_active_runs == 1
    for dataset in ("recently_played", "top_tracks", "top_artists"):
        extract = dag.get_task(f"extract_{dataset}")
        assert extract.downstream_task_ids == {f"process_{dataset}"}
        assert (
            extract.retries == 3 and extract.execution_timeout.total_seconds() == 1200
        )
