-- Calendar: one row per day, so charts can group by weekday, month or weekend.

select
    day                                as date_key,
    extract(year from day)             as year,
    extract(month from day)            as month,
    format_date('%B', day)             as month_name,
    format_date('%A', day)             as weekday_name,
    extract(dayofweek from day) in (1, 7) as is_weekend
from unnest(
    generate_date_array(
        date('{{ var("calendar_start") }}'),
        current_date('{{ var("site_timezone") }}')
    )
) as day
