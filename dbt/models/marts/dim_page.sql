-- Every page that received traffic, with article details where the page is an article.

with pages as (
    select distinct page_path
    from {{ ref('stg_ga4__page_traffic') }}
)

select
    pages.page_path,
    case
        when articles.page_path is not null then 'article'
        when pages.page_path = '/' then 'home'
        else 'other'
    end                                                          as page_type,
    articles.title,
    articles.author,
    articles.primary_category,
    articles.published_at,
    date(articles.published_at, '{{ var("site_timezone") }}')   as published_date
from pages
left join {{ ref('stg_rss__articles') }} as articles
    on pages.page_path = articles.page_path
