-- The numbers: one row per day, hour, page, traffic source and device.
-- Source, medium, channel and device stay as plain columns: they have few values
-- and need no table of their own.
-- active_users can not be added up across rows: one person visiting in two hours
-- is counted in both. Use page_views and sessions for totals.

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
