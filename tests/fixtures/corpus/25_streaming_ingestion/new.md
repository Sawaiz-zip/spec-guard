# Sales ETL Pipeline

A batch ETL pipeline that ingests daily CSV sales reports into a PostgreSQL
warehouse.

## Ingestion

Sales events stream into a Kafka topic and are consumed continuously;
the nightly CSV drop is retired.

## Validation

Each file is checked for schema drift, duplicate order IDs, and currency
formatting errors before load. Files that fails validation is quarantined.

## Loading

Validated rows are bulk-loaded into the PostgreSQL warehouse inside a single
transaction per file, so a failed load never leaves partial data behind.

## Scheduling

The pipeline runs once per day at 02:00 UTC via cron. A late-arriving file is
picked up on the next run.

## Data quality

Post-load checks compare daily totals against the source manifest.
