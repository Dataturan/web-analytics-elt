"""Daily pipeline: load RSS and GA4 into BigQuery, then build the dbt models.

Each task runs a command with the project's own Python environment, after loading
the settings from .env. Airflow only schedules and retries the steps.
"""

from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

PROJECT = Path(__file__).resolve().parents[2]  # airflow/dags/this_file.py -> project folder
VENV = PROJECT / ".venv" / "bin"
SETUP = f"cd {PROJECT} && set -a && . ./.env && set +a && "

with DAG(
    dag_id="web_analytics_daily",
    schedule="0 22 * * *",  # every day at 10:00
    start_date=pendulum.datetime(2026, 10, 20, tz="Europe/Amsterdam"),
    catchup=False,  # each run re-pulls the last 3 days, so missed days fill themselves in
    default_args={"retries": 2, "retry_delay": timedelta(minutes=10)},
):
    extract_rss = BashOperator(
        task_id="extract_rss",
        bash_command=SETUP + f"{VENV}/python -m extract.rss_extract",
    )
    extract_ga4 = BashOperator(
        task_id="extract_ga4",
        bash_command=SETUP + f"{VENV}/python -m extract.ga4_extract",
    )
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=SETUP + f"cd dbt && {VENV}/dbt build",
    )

    [extract_rss, extract_ga4] >> dbt_build
