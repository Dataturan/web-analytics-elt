-- One row per article: the most recent version seen in the daily snapshots or the archive.
-- The first category in the feed is the WordPress category, the rest are tags.

with all_snapshots as (
    select * from {{ source('raw', 'rss_articles') }}
    union all
    select * from {{ source('raw', 'rss_articles_history') }}
),

ranked as (
    select
        *,
        row_number() over (
            partition by page_path_normalized
            order by extracted_at desc
        ) as row_num
    from all_snapshots
    where page_path_normalized is not null
)

select
    page_path_normalized       as page_path,
    url,
    title,
    author,
    categories[safe_offset(0)] as primary_category,
    published_at,
    extracted_at               as last_seen_at
from ranked
where row_num = 1
