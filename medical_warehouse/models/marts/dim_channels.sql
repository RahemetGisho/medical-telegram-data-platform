{{
  config(
    materialized='table',
    tags=['marts', 'production', 'daily'],
    meta={
      'owner': 'analytics_team',
      'description': 'Dimension table for telegram channels with metadata and aggregates'
    }
  )
}}


WITH channel_metrics AS (
  SELECT
    channel_name,
    COUNT(*) AS total_messages,
    COUNT(CASE WHEN has_image THEN 1 END) AS total_images,
    COUNT(DISTINCT DATE(message_date)) AS active_days,
    MIN(message_date) AS first_post_date,
    MAX(message_date) AS last_post_date,
    ROUND(AVG(CAST(views AS NUMERIC)), 2) AS avg_views,
    ROUND(AVG(CAST(forwards AS NUMERIC)), 2) AS avg_forwards,
    ROUND(AVG(CAST(total_engagement AS NUMERIC)), 2) AS avg_engagement,
    MAX(views) AS max_views,
    MAX(forwards) AS max_forwards,
    ROUND(
      CAST(COUNT(CASE WHEN has_image THEN 1 END) AS NUMERIC)
      / NULLIF(COUNT(*), 0) * 100,
      2
    ) AS image_ratio_pct
  FROM {{ ref('stg_telegram_messages') }}
  GROUP BY channel_name
),

channels_with_type AS (
  SELECT
    ROW_NUMBER() OVER (ORDER BY total_messages DESC) AS channel_key,
    channel_name,

    CASE 
      WHEN LOWER(channel_name) LIKE '%pharma%' THEN 'Pharmaceutical'
      WHEN LOWER(channel_name) LIKE '%cosmetic%' THEN 'Cosmetics'
      WHEN LOWER(channel_name) LIKE '%med%' THEN 'Medical'
      ELSE 'Other'
    END AS channel_type,

    total_messages,
    total_images,
    active_days,
    first_post_date,
    last_post_date,
    avg_views,
    avg_forwards,
    avg_engagement,
    max_views,
    max_forwards,
    image_ratio_pct,

-- ✅ PostgreSQL correct date difference


CASE 
      WHEN (CURRENT_DATE - last_post_date::date) <= 3 THEN 'Active'
      WHEN (CURRENT_DATE - last_post_date::date) <= 30 THEN 'Moderate'
      ELSE 'Inactive'
    END AS activity_status,

    CURRENT_TIMESTAMP AS dim_created_at,
    CURRENT_TIMESTAMP AS dim_updated_at

  FROM channel_metrics
)

SELECT * FROM channels_with_type