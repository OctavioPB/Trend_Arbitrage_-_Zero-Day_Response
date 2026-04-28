"""Golden record DAG — stub. Full implementation in Sprint 4.

Triggered when MPI crosses the threshold for a topic cluster.
Will call predictive.golden_record_generator to build and persist golden records.
"""

from datetime import timedelta

from airflow.decorators import dag, task
from airflow.utils.dates import days_ago

_DEFAULT_ARGS = {
    "owner": "trend-arbitrage",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}


@dag(
    dag_id="golden_record",
    schedule="*/5 * * * *",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    default_args=_DEFAULT_ARGS,
    tags=["predictive"],
    doc_md=__doc__,
)
def golden_record_dag() -> None:
    @task()
    def placeholder() -> None:
        pass  # Sprint 4 wires the real generator here

    placeholder()


golden_record_dag()
