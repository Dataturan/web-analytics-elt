# Web Analytics Pipeline

A small daily pipeline that pulls website traffic and article data into BigQuery
and turns it into a few clean tables I can query and chart.

## Why

This is built to get practical experience with BigQuery, Google Cloud, dbt and Airflow. For a simple traffic dashboard, connecting Looker Studio straight to Google Analytics would be enough. What this pipeline adds is the article data (writer, category, publish time) joined to the traffic, the full history in my own warehouse, and tested tables I can query with SQL

## Is this the right way to do it?

Honestly, no. If I only wanted the numbers, I'd switch on the GA4 export to BigQuery, send category and author to GA4 directly and put Looker Studio on top. No RSS, no Airflow on my laptop. This project is overbuilt on purpose, because the point was to learn BigQuery, dbt and Airflow by using them on real data. But it works 

## How it works

    GA4 + RSS feed  ->  Python  ->  BigQuery  ->  dbt  ->  Looker Studio
                        (Airflow runs it every night)

- **Python** pulls the traffic from Google Analytics (per hour, page, source and device)
  and the article list from the RSS feed, and loads both into BigQuery.
- **dbt** cleans the raw data and builds one fact table with page views and two small
  tables for pages and dates. It only rebuilds the last 3 days each run, since Google
  Analytics keeps updating those for a while.
- **dbt tests** check that the keys are unique and that every traffic row matches a page and a date.
- **Airflow** runs the whole thing every night at 22:00 on my own machine.
- **Looker Studio** has a private dashboard on top: busiest hours and days, top
  categories and articles, where readers come from.
- **GitHub Actions** runs ruff and a small test on every push.

## Privacy

No data, IDs or passwords are in this repo. Settings are in a local `.env` file
(`.env.example` shows which ones). The pipeline uses a service account with only the
access it needs and no key files.

## Stack

Python, Google Cloud, BigQuery, dbt, Airflow, Looker Studio, GitHub Actions