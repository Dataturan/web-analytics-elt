"""Extract daily page traffic from the GA4 Data API into BigQuery.

Two modes:

  python -m extract.ga4_extract                              last 3 days (daily run)
  python -m extract.ga4_extract --backfill-from 2026-06-01   every day since that date

One row per day, page, traffic source and device. Each day is loaded into its
own partition and replaces what was there, so re-running a day never doubles it.
The daily run re-fetches the last few days because GA4 keeps revising them.
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, date, datetime, timedelta

from extract.common import (
    Config,
    bigquery_client,
    ensure_partitioned_table,
    load_config,
    normalize_path,
    replace_partition,
)

log = logging.getLogger(__name__)

TABLE = "ga4_page_traffic"

DIMENSIONS = [
    "date",
    "pagePath",
    "sessionSource",
    "sessionMedium",
    "sessionDefaultChannelGroup",
    "deviceCategory",
]
METRICS = ["screenPageViews", "activeUsers", "sessions", "userEngagementDuration"]

# GA4 name -> column name in BigQuery
COLUMN_NAMES = {
    "pagePath": "page_path",
    "sessionSource": "source",
    "sessionMedium": "medium",
    "sessionDefaultChannelGroup": "channel_group",
    "deviceCategory": "device_category",
    "screenPageViews": "page_views",
    "activeUsers": "active_users",
    "sessions": "sessions",
    "userEngagementDuration": "engagement_seconds",
}
INT_COLUMNS = {"page_views", "active_users", "sessions"}

PAGE_SIZE = 100_000


def bq_schema():
    from google.cloud.bigquery import SchemaField

    return [
        SchemaField("report_date", "DATE", mode="REQUIRED"),
        SchemaField("page_path", "STRING"),
        SchemaField("page_path_normalized", "STRING"),
        SchemaField("source", "STRING"),
        SchemaField("medium", "STRING"),
        SchemaField("channel_group", "STRING"),
        SchemaField("device_category", "STRING"),
        SchemaField("page_views", "INT64"),
        SchemaField("active_users", "INT64"),
        SchemaField("sessions", "INT64"),
        SchemaField("engagement_seconds", "FLOAT64"),
        SchemaField("loaded_at", "TIMESTAMP", mode="REQUIRED"),
    ]


def fetch_day(client, property_id: str, day: date) -> list[tuple[list[str], list[str]]]:
    """Ask GA4 for one day of traffic, in pages if the answer is large."""
    from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest

    rows = []
    offset = 0
    while True:
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[Dimension(name=d) for d in DIMENSIONS],
            metrics=[Metric(name=m) for m in METRICS],
            date_ranges=[DateRange(start_date=day.isoformat(), end_date=day.isoformat())],
            limit=PAGE_SIZE,
            offset=offset,
        )
        response = client.run_report(request)
        for row in response.rows:
            dims = [v.value for v in row.dimension_values]
            mets = [v.value for v in row.metric_values]
            rows.append((dims, mets))
        offset += PAGE_SIZE
        if offset >= response.row_count:
            return rows


def to_records(rows, loaded_at: datetime) -> list[dict]:
    """Turn GA4 rows into dicts that match the BigQuery table."""
    records = []
    for dims, mets in rows:
        record = {"loaded_at": loaded_at.isoformat()}
        for name, value in zip(DIMENSIONS, dims, strict=True):
            if name == "date":  # GA4 sends 20261014, BigQuery wants 2026-10-14
                record["report_date"] = f"{value[:4]}-{value[4:6]}-{value[6:]}"
            else:
                record[COLUMN_NAMES[name]] = value
        for name, value in zip(METRICS, mets, strict=True):
            column = COLUMN_NAMES[name]
            record[column] = int(float(value)) if column in INT_COLUMNS else float(value)
        record["page_path_normalized"] = normalize_path(record["page_path"])
        records.append(record)
    return records


def load_days(cfg: Config, days: list[date]) -> int:
    """Fetch each day from GA4 and replace that day's partition in BigQuery."""
    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    ga4 = BetaAnalyticsDataClient()
    bq = bigquery_client(cfg)
    schema = bq_schema()
    table_id = ensure_partitioned_table(bq, cfg, TABLE, schema, "report_date")

    loaded_at = datetime.now(UTC)
    total = 0
    for day in days:
        records = to_records(fetch_day(ga4, cfg.ga4_property_id, day), loaded_at)
        total += replace_partition(bq, table_id, schema, day, records)
    log.info("GA4 extract finished: %d rows across %d days", total, len(days))
    return total


def days_between(start: date, end: date) -> list[date]:
    """Every day from start to end, both included."""
    return [start + timedelta(days=n) for n in range((end - start).days + 1)]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Load GA4 page traffic into BigQuery.")
    parser.add_argument("--backfill-from", type=date.fromisoformat, help="first day, YYYY-MM-DD")
    args = parser.parse_args()

    cfg = load_config()
    yesterday = date.today() - timedelta(days=1)
    first_day = args.backfill_from or yesterday - timedelta(days=cfg.lookback_days - 1)
    load_days(cfg, days_between(first_day, yesterday))
