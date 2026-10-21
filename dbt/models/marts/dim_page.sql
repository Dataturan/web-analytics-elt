-- Every page that received traffic, with article details where the page is an article.
-- Categories: the feed lists subcategories and main categories in no fixed order, so the
-- private seed category_parents (subcategory -> main category) decides which is which.

with pages as (
    select distinct page_path
    from {{ ref('stg_ga4__page_traffic') }}
),

articles as (
    select * from {{ ref('stg_rss__articles') }}
),

subcategory_match as (
    select
        articles.page_path,
        parents.sub_category,
        parents.main_category,
        row_number() over (partition by articles.page_path order by position) as match_order
    from articles
    cross join unnest(articles.categories) as category with offset as position
    join {{ ref('category_parents') }} as parents
        on parents.sub_category = category
)

select
    pages.page_path,
    case
        when articles.page_path is not null then 'article'
        when pages.page_path = '/' then 'home'
        else 'other'
    end                                                                   as page_type,
    articles.title,
    articles.author,
    coalesce(subcategory_match.main_category, articles.categories[safe_offset(0)])
                                                                          as main_category,
    subcategory_match.sub_category,
    articles.published_at,
    date(articles.published_at, '{{ var("site_timezone") }}')            as published_date
from pages
left join articles
    on pages.page_path = articles.page_path
left join subcategory_match
    on pages.page_path = subcategory_match.page_path
    and subcategory_match.match_order = 1
