# SQL Cookbook

Everyday queries against the analytics warehouse.

## Sessionization

```sql
WITH events AS (
  SELECT
    user_id,
    occurred_at,
    occurred_at - LAG(occurred_at) OVER (
      PARTITION BY user_id ORDER BY occurred_at
    ) AS gap
  FROM raw.events
  WHERE occurred_at >= CURRENT_DATE - INTERVAL '7 days'
)
SELECT
  user_id,
  occurred_at,
  SUM(CASE WHEN gap > INTERVAL '30 minutes' THEN 1 ELSE 0 END)
    OVER (PARTITION BY user_id ORDER BY occurred_at) AS session_id
FROM events;
```

## Retention

```sql
SELECT
  cohort_week,
  COUNT(DISTINCT user_id) AS cohort_size,
  COUNT(DISTINCT active_in_week_4) AS retained_4
FROM metrics.cohorts
GROUP BY cohort_week
ORDER BY cohort_week DESC;
```

## Index Audit

```sql
SELECT
  relname AS table_name,
  indexrelname AS index_name,
  idx_scan,
  idx_tup_read
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY idx_tup_read DESC;
```

## Vacuum Schedule

Run the maintenance window weekly. Tables larger than 200 GiB switch to
autovacuum tuning instead of full vacuum.
