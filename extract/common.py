"""Shared helpers: configuration, path normalisation and BigQuery loading.

Logging rule for this project: only log counts and dates, never row contents.
CI and Airflow logs can be public, so no data should ever be printed.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from urllib.parse import unquote, urlparse

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    gcp_project: str
    raw_dataset: str
    location: str
    ga4_property_id: str
    rss_url: str
    lookback_days: int


def load_config() -> Config:
    """Read settings from environment variables (or a local .env file)."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    def required(name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return value

    return Config(
        gcp_project=required("GCP_PROJECT"),
        raw_dataset=os.environ.get("BQ_RAW_DATASET", "raw"),
        location=os.environ.get("BQ_LOCATION", "EU"),
        ga4_property_id=required("GA4_PROPERTY_ID"),
        rss_url=required("RSS_URL"),
        lookback_days=int(os.environ.get("LOOKBACK_DAYS", "3")),
    )


def normalize_path(url_or_path: str | None) -> str | None:
    """Turn a full URL or a GA4 pagePath into one comparable form.

    GA4 reports paths ("/haber/some-slug/") while RSS gives full URLs
    ("https://example.com/haber/some-slug/"). Both are reduced to a lowercase,
    URL-decoded path without query string and without trailing slash, so the
    two sources can be joined.
    """
    if not url_or_path:
        return None
    path = urlparse(url_or_path.strip()).path or "/"
    path = unquote(path).lower()
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 1:
        path = path.rstrip("/")
    return path


def bigquery_client(cfg: Config):
    from google.cloud import bigquery

    return bigquery.Client(project=cfg.gcp_project, location=cfg.location)


def ensure_partitioned_table(client, cfg: Config, table: str, schema, partition_field: str) -> str:
    """Create the dataset and a date-partitioned table if they don't exist yet."""
    from google.cloud import bigquery

    dataset_id = f"{cfg.gcp_project}.{cfg.raw_dataset}"
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = cfg.location
    client.create_dataset(dataset, exists_ok=True)

    table_id = f"{dataset_id}.{table}"
    tbl = bigquery.Table(table_id, schema=schema)
    tbl.time_partitioning = bigquery.TimePartitioning(field=partition_field)
    client.create_table(tbl, exists_ok=True)
    return table_id


def replace_partition(
    client, table_id: str, schema, partition_day: date, records: list[dict]
) -> int:
    """Overwrite one day's partition with the given records.

    Writing with WRITE_TRUNCATE to the "table$YYYYMMDD" partition makes every
    load idempotent: running the same day twice gives the same result, and
    re-fetching recent days replaces GA4's earlier, still-changing numbers.
    """
    from google.cloud import bigquery

    target = f"{table_id}${partition_day:%Y%m%d}"
    if not records:
        client.delete_table(target, not_found_ok=True)
        log.info("No rows for %s, partition cleared", partition_day)
        return 0

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )
    client.load_table_from_json(records, target, job_config=job_config).result()
    log.info("Loaded %d rows into partition %s", len(records), partition_day)
    return len(records)
