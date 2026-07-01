{{
  config(
    materialized='table',
    tags=['marts', 'production', 'daily'],
    meta={
      'owner': 'analytics_team',
      'description': 'Central fact table for message analytics',
      'freshness': 'daily'
    }
  )
}}


WITH stg_messages AS (
  SELECT
    message_id,
    channel_name,
    message_date,
    message_date_utc,
    message_text,
    message_length,
    has_media,
    has_image,
    image_path,
    views,
    forwards,
    reactions,
    total_engagement,
    is_valid_message
  FROM {{ ref('stg_telegram_messages') }}
),

dim_channels AS (
  SELECT
    channel_key,
    channel_name
  FROM {{ ref('dim_channels') }}
),

dim_dates AS (
  SELECT
    date_key,
    calendar_date
  FROM {{ ref('dim_dates') }}
),

joined_data AS (
  SELECT
    -- Keys
    ROW_NUMBER() OVER (ORDER BY m.message_id) AS message_sk,
    m.message_id,
    dc.channel_key,
    dd.date_key,

-- Message fields
m.message_text,
m.message_length,
m.has_media,
m.has_image,
m.image_path,

-- Metrics
m.views, m.forwards, m.reactions, m.total_engagement,

-- Engagement classification
CASE
    WHEN m.views = 0
    AND m.forwards = 0
    AND m.reactions = 0 THEN 'No Engagement'
    WHEN m.views < 10 THEN 'Low Engagement'
    WHEN m.views < 50 THEN 'Medium Engagement'
    WHEN m.views < 200 THEN 'High Engagement'
    ELSE 'Viral'
END AS engagement_level,

-- Content type
CASE
    WHEN m.has_image
    AND m.message_length > 0 THEN 'Text + Image'
    WHEN m.has_image THEN 'Image Only'
    WHEN m.message_length > 0 THEN 'Text Only'
    ELSE 'Empty Message'
END AS content_type,

-- Data quality
m.is_valid_message,
CASE
    WHEN m.views < 0
    OR m.forwards < 0
    OR m.reactions < 0 THEN TRUE
    ELSE FALSE
END AS has_data_anomaly,

-- Time features
m.message_date,
m.message_date_utc,
EXTRACT(
    HOUR
    FROM m.message_date_utc
) AS post_hour,
EXTRACT(
    DOW
    FROM m.message_date
) AS post_day_of_week,

-- Metadata

CURRENT_TIMESTAMP AS fact_created_at,
    CURRENT_TIMESTAMP AS fact_updated_at

  FROM stg_messages m
  INNER JOIN dim_channels dc
    ON m.channel_name = dc.channel_name
  INNER JOIN dim_dates dd
    ON m.message_date::date = dd.calendar_date
)

SELECT * FROM joined_data