{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'date_key', 'data_type': 'date'}
) }}

-- The numbers: one row per day, hour, page, traffic source and device.
-- Source, medium, channel and device stay as plain columns: they have few values
-- and need no table of their own.
-- active_users can not be added up across rows: one person visiting in two hours
-- is counted in both. Use page_views and sessions for totals.
-- Incremental: after the first build, each run only replaces the last few days,
-- because GA4 keeps revising them. Older days are final and stay untouched.

select
    report_date as date_key,
    report_hour as hour,
    page_path,
    source,
    medium,
    channel_group,
    device_category,
    page_views,
    sessions,
    active_users,
    engagement_seconds
from {{ ref('stg_ga4__page_traffic') }}

{% if is_incremental() %}
where report_date >= date_sub(
    current_date('{{ var("site_timezone") }}'),
    interval {{ var("lookback_days") }} day
)
{% endif %}