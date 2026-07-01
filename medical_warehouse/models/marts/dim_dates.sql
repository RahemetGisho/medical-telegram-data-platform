{{
  config(
    materialized='table',
    tags=['marts', 'production'],
    meta={
      'owner': 'analytics_team',
      'description': 'Standard date dimension for analytical queries'
    }
  )
}}


WITH date_spine AS (
  SELECT 
    generate_series(
      (SELECT DATE_TRUNC('day', MIN(message_date))::date FROM {{ ref('stg_telegram_messages') }}),
      CURRENT_DATE,
      interval '1 day'
    )::date AS calendar_date
),

dates_with_attributes AS (
  SELECT
    -- Key
    ROW_NUMBER() OVER (ORDER BY calendar_date) AS date_key,
    calendar_date,

-- Date components (Postgres style)
EXTRACT(YEAR FROM calendar_date)::int AS year,
    EXTRACT(MONTH FROM calendar_date)::int AS month,
    EXTRACT(DAY FROM calendar_date)::int AS day_of_month,
    EXTRACT(DOW FROM calendar_date)::int AS day_of_week_num,  -- 0=Sunday

-- Names
TO_CHAR (calendar_date, 'YYYY-MM-DD') AS date_formatted,
TO_CHAR (calendar_date, 'Month') AS month_name,
CASE EXTRACT(
        DOW
        FROM calendar_date
    )
    WHEN 0 THEN 'Sunday'
    WHEN 1 THEN 'Monday'
    WHEN 2 THEN 'Tuesday'
    WHEN 3 THEN 'Wednesday'
    WHEN 4 THEN 'Thursday'
    WHEN 5 THEN 'Friday'
    WHEN 6 THEN 'Saturday'
END AS day_name,

-- Week info
EXTRACT(WEEK FROM calendar_date)::int AS week_of_year,
    DATE_TRUNC('week', calendar_date)::date AS week_start_date,
    (DATE_TRUNC('week', calendar_date) + interval '6 days')::date AS week_end_date,

-- Quarter
CEIL(EXTRACT(MONTH FROM calendar_date) / 3.0)::int AS quarter,
    'Q' || CEIL(EXTRACT(MONTH FROM calendar_date) / 3.0)::int || ' ' || EXTRACT(YEAR FROM calendar_date)::int AS quarter_name,

-- Flags
CASE WHEN EXTRACT(DOW FROM calendar_date) IN (0, 6) THEN TRUE ELSE FALSE END AS is_weekend,
    CASE WHEN calendar_date = CURRENT_DATE THEN TRUE ELSE FALSE END AS is_today,
    CASE WHEN DATE_TRUNC('month', calendar_date)::date = calendar_date THEN TRUE ELSE FALSE END AS is_first_day_of_month,
    CASE WHEN (calendar_date + interval '1 day')::date > (DATE_TRUNC('month', calendar_date + interval '1 month'))::date
         THEN TRUE ELSE FALSE END AS is_last_day_of_month,

-- Days since start

(calendar_date - DATE '2024-01-01') AS days_since_start,

    CURRENT_TIMESTAMP AS dim_created_at

  FROM date_spine
)

SELECT * FROM dates_with_attributes ORDER BY calendar_date