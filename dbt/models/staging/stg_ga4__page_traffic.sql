-- GA4 traffic with clean names. One row per day, hour, page, source, medium, channel and device.
-- Different raw URLs of the same page (for example with ?utm tags) are added together here,
-- so each cleaned page path appears once per combination.

select
    report_date,
    report_hour,
    coalesce(page_path_normalized, '(not set)')        as page_path,
    coalesce(nullif(source, ''), '(not set)')          as source,
    coalesce(nullif(medium, ''), '(not set)')          as medium,
    coalesce(nullif(channel_group, ''), '(not set)')   as channel_group,
    coalesce(nullif(device_category, ''), '(not set)') as device_category,
    sum(page_views)                                    as page_views,
    sum(sessions)                                      as sessions,
    sum(active_users)                                  as active_users,
    sum(engagement_seconds)                            as engagement_seconds,
    max(loaded_at)                                     as loaded_at
from {{ source('raw', 'ga4_page_traffic') }}
group by 1, 2, 3, 4, 5, 6, 7
