"""Extract article metadata from the site's public RSS feed into BigQuery.

Two modes:

  python -m extract.rss_extract              daily snapshot of the feed
  python -m extract.rss_extract --backfill   one-time load of the full history

The feed only lists the most recent articles, so the daily run stores a
snapshot per day. The backfill walks the feed's older pages (?paged=2, 3, ...)
once, slowly, and stores everything in a separate history table. It then
cross-checks the result against the sitemap, which lists every article URL.
"""

from __future__ import annotations

import argparse
import calendar
import logging
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from extract.common import (
    Config,
    bigquery_client,
    ensure_partitioned_table,
    load_config,
    normalize_path,
    replace_partition,
)

log = logging.getLogger(__name__)

TABLE = "rss_articles"
HISTORY_TABLE = "rss_articles_history"
USER_AGENT = "web-analytics-elt/1.0 (+daily metadata fetch)"


def bq_schema():
    from google.cloud.bigquery import SchemaField

    return [
        SchemaField("extracted_date", "DATE", mode="REQUIRED"),
        SchemaField("url", "STRING"),
        SchemaField("page_path_normalized", "STRING"),
        SchemaField("guid", "STRING"),
        SchemaField("title", "STRING"),
        SchemaField("author", "STRING"),
        SchemaField("categories", "STRING", mode="REPEATED"),
        SchemaField("published_at", "TIMESTAMP"),
        SchemaField("extracted_at", "TIMESTAMP", mode="REQUIRED"),
    ]


def _to_utc_iso(struct_time) -> str | None:
    if not struct_time:
        return None
    return datetime.fromtimestamp(calendar.timegm(struct_time), tz=UTC).isoformat()


def entries_to_records(entries, extracted_at: datetime) -> list[dict]:
    """Convert parsed feed entries into dicts matching the BigQuery schema."""
    records = []
    for entry in entries:
        link = entry.get("link")
        records.append(
            {
                "extracted_date": extracted_at.date().isoformat(),
                "url": link,
                "page_path_normalized": normalize_path(link),
                "guid": entry.get("id") or link,
                "title": entry.get("title"),
                "author": entry.get("author"),
                "categories": [t.get("term") for t in entry.get("tags", []) if t.get("term")],
                "published_at": _to_utc_iso(entry.get("published_parsed")),
                "extracted_at": extracted_at.isoformat(),
            }
        )
    return [r for r in records if r["page_path_normalized"]]


def parse_feed(source: str):
    """Parse a feed from a URL or a local file path."""
    import feedparser

    feed = feedparser.parse(source, agent=USER_AGENT)
    if feed.get("bozo") and not feed.entries:
        raise RuntimeError(f"Could not parse RSS feed: {feed.get('bozo_exception')}")
    return feed.entries


# Daily run


def run(cfg: Config | None = None) -> int:
    cfg = cfg or load_config()
    extracted_at = datetime.now(UTC)
    records = entries_to_records(parse_feed(cfg.rss_url), extracted_at)

    bq = bigquery_client(cfg)
    schema = bq_schema()
    table_id = ensure_partitioned_table(bq, cfg, TABLE, schema, "extracted_date")
    count = replace_partition(bq, table_id, schema, extracted_at.date(), records)
    log.info("RSS extract finished: %d articles", count)
    return count


# One-time backfill


def page_url(feed_url: str, page: int) -> str:
    """URL of a given feed page. Page 1 is the normal feed, then ?paged=2, 3, ..."""
    if page <= 1:
        return feed_url
    parts = urlsplit(feed_url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "paged"]
    query.append(("paged", str(page)))
    return urlunsplit(parts._replace(query=urlencode(query)))


def fetch_feed_page(url: str):
    """Fetch one feed page. Returns (HTTP status, entries)."""
    import feedparser

    feed = feedparser.parse(url, agent=USER_AGENT)
    return feed.get("status", 200), feed.entries


def collect_history(feed_url: str, delay_seconds: float, max_pages: int, fetch=fetch_feed_page):
    """Walk the feed pages until one is empty, missing or only repeats known articles.

    Waits `delay_seconds` between requests so the site barely notices, and stops
    at `max_pages` as a safety limit. Entries are de-duplicated by path.
    """
    seen: dict[str, object] = {}
    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(delay_seconds)
        status, entries = fetch(page_url(feed_url, page))
        if status >= 400 or not entries:
            log.info("Feed page %d returned no entries (status %s), stopping", page, status)
            break
        new = 0
        for entry in entries:
            key = normalize_path(entry.get("link"))
            if key and key not in seen:
                seen[key] = entry
                new += 1
        log.info("Feed page %d: %d entries, %d new", page, len(entries), new)
        if new == 0:
            log.info("Page %d only repeated known articles, stopping", page)
            break
    else:
        log.warning("Stopped at the safety limit of %d pages", max_pages)
    return list(seen.values())


def sitemap_locs(xml_text: str) -> list[str]:
    """All <loc> values in a sitemap or sitemap index, whatever the namespace."""
    root = ET.fromstring(xml_text)
    return [el.text.strip() for el in root.iter() if el.tag.endswith("loc") and el.text]


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def sitemap_article_paths(feed_url: str, fetch=fetch_text) -> set[str]:
    """Normalized paths of all posts listed in the site's sitemap index."""
    parts = urlsplit(feed_url)
    index_url = f"{parts.scheme}://{parts.netloc}/sitemap_index.xml"
    post_sitemaps = [loc for loc in sitemap_locs(fetch(index_url)) if "post-sitemap" in loc]
    paths: set[str] = set()
    for loc in post_sitemaps:
        paths.update(normalize_path(u) for u in sitemap_locs(fetch(loc)))
    paths.discard("/")
    paths.discard(None)
    return paths


def compare_paths(feed_paths: set[str], sitemap_paths: set[str]) -> dict[str, int]:
    """Counts only, so the result is safe to log."""
    return {
        "feed": len(feed_paths),
        "sitemap": len(sitemap_paths),
        "in_both": len(feed_paths & sitemap_paths),
        "missing_from_feed": len(sitemap_paths - feed_paths),
        "not_in_sitemap": len(feed_paths - sitemap_paths),
    }


def replace_table(client, cfg: Config, table: str, schema, records: list[dict]) -> int:
    """Create or fully overwrite a small table. Re-running gives the same result."""
    from google.cloud import bigquery

    dataset = bigquery.Dataset(f"{cfg.gcp_project}.{cfg.raw_dataset}")
    dataset.location = cfg.location
    client.create_dataset(dataset, exists_ok=True)
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )
    table_id = f"{cfg.gcp_project}.{cfg.raw_dataset}.{table}"
    client.load_table_from_json(records, table_id, job_config=job_config).result()
    return len(records)


def backfill(cfg: Config | None = None, delay_seconds: float = 5, max_pages: int = 300) -> int:
    cfg = cfg or load_config()
    extracted_at = datetime.now(UTC)
    entries = collect_history(cfg.rss_url, delay_seconds, max_pages)
    records = entries_to_records(entries, extracted_at)

    count = replace_table(bigquery_client(cfg), cfg, HISTORY_TABLE, bq_schema(), records)
    log.info("RSS backfill loaded %d articles into %s", count, HISTORY_TABLE)

    try:
        feed_paths = {r["page_path_normalized"] for r in records}
        check = compare_paths(feed_paths, sitemap_article_paths(cfg.rss_url))
        log.info("Sitemap cross-check: %s", check)
    except Exception as exc:  # informative only, never fail the load on it
        log.warning("Sitemap cross-check skipped: %s", type(exc).__name__)
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Load RSS article metadata into BigQuery.")
    parser.add_argument("--backfill", action="store_true", help="one-time load of all pages")
    parser.add_argument("--delay", type=float, default=5, help="seconds between page requests")
    args = parser.parse_args()
    if args.backfill:
        backfill(delay_seconds=args.delay)
    else:
        run()
