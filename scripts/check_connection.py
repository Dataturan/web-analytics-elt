"""Check that the pipeline can reach BigQuery and GA4 before building anything.

Run from the project root:  python -m scripts.check_connection

It prints only OK/FAIL lines and counts, never data, IDs or tokens, so the
output is safe to share when asking for help.
"""

from __future__ import annotations

import sys

from extract.common import load_config


def check_identity() -> bool:
    import google.auth

    try:
        credentials, _ = google.auth.default()
    except Exception as exc:
        print(f"FAIL  login: {type(exc).__name__}. Run the gcloud application-default login.")
        return False
    account = getattr(credentials, "service_account_email", None) or getattr(
        credentials, "_target_principal", None
    )
    if account:
        print(f"OK    acting as service account '{account.split('@')[0]}'")
    else:
        print("WARN  logged in, but not as a service account (impersonation not set?)")
    return True


def check_bigquery(cfg) -> bool:
    from google.cloud import bigquery

    try:
        client = bigquery.Client(project=cfg.gcp_project, location=cfg.location)
        job_config = bigquery.QueryJobConfig(maximum_bytes_billed=10**9)
        rows = list(client.query("select 1 as ok", job_config=job_config).result())
        datasets = list(client.list_datasets())
    except Exception as exc:
        print(f"FAIL  BigQuery: {type(exc).__name__}: {str(exc).splitlines()[0][:150]}")
        return False
    print(f"OK    BigQuery: test query returned {len(rows)} row, {len(datasets)} dataset(s)")
    return True


def check_ga4(cfg) -> bool:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    try:
        client = BetaAnalyticsDataClient()
        metadata = client.get_metadata(name=f"properties/{cfg.ga4_property_id}/metadata")
    except Exception as exc:
        print(f"FAIL  GA4: {type(exc).__name__}: {str(exc).splitlines()[0][:150]}")
        return False
    print(
        f"OK    GA4: property reachable, {len(metadata.dimensions)} dimensions and "
        f"{len(metadata.metrics)} metrics available"
    )
    return True


def main() -> int:
    cfg = load_config()
    results = [check_identity(), check_bigquery(cfg), check_ga4(cfg)]
    print("All checks passed." if all(results) else "Some checks failed, see above.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
