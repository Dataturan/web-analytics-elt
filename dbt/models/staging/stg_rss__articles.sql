-- One row per article: the most recent version seen in the daily snapshots or the archive.
-- categories holds the WordPress categories and tags of the article, as listed in the feed.

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
    categories,
    published_at,
    extracted_at               as last_seen_at
from ranked
where row_num = 1
