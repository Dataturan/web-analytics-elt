# Web Analytics ELT Pipeline

A daily ELT pipeline that loads a news website's traffic (GA4 Data API) and article
metadata (RSS) into BigQuery, models it with dbt into a tested star schema, and runs
it with Apache Airflow.

**Status:** work in progress, built step by step. This README grows with the project.

## Planned architecture

```
GA4 Data API ─┐
              ├─> Python extract ─> BigQuery raw ─> dbt staging ─> dbt marts (star schema)
RSS feed ─────┘                                                  └> dbt features
                     orchestrated by Airflow · checked by GitHub Actions
```

## Security and privacy

- No credentials in the repository. The pipeline uses **service account impersonation**:
  short-lived tokens, no key files.
- The service account has only BigQuery Data Editor and Job User on its own project,
  and read-only (Viewer) access to Analytics, without cost or revenue metrics.
- No data, IDs or secrets are committed. All settings come from a local `.env` file
  (see `.env.example`), and logs print counts only.

## Local setup

Requires Python 3.13 and the Google Cloud CLI.

```bash
uv venv .venv --python 3.13
source .venv/bin/activate
uv pip install -r requirements-dev.txt
cp .env.example .env          # then fill in your own values
python -m scripts.check_connection
```
