{{
  config(
    materialized='view',
    tags=['staging', 'daily'],
    meta={
      'owner': 'analytics_team',
      'description': 'Cleaned and standardized telegram messages from raw layer'
    }
  )
}}


WITH source_data AS (
  SELECT
    message_id,
    channel_name,
    message_date,
    message_text,
    has_media,
    image_path,
    views,
    forwards,
    reactions,
    loaded_at
  FROM {{ source('raw', 'telegram_messages') }}
  WHERE message_id IS NOT NULL
    AND channel_name IS NOT NULL
    AND message_date IS NOT NULL
),

cleaned_data AS (
  SELECT
    -- Primary Key
    message_id,

-- Channel Information
TRIM(channel_name) AS channel_name,

-- Temporal Information
message_date::TIMESTAMP AT TIME ZONE 'UTC' AS message_date_utc,
    DATE(message_date) AS message_date,

-- Message Content
TRIM(COALESCE(message_text, '')) AS message_text,

-- compute once (no alias reuse issue)
LENGTH( TRIM(COALESCE(message_text, '')) ) AS message_length,

-- Media Information
COALESCE(has_media, FALSE) AS has_media,
CASE
    WHEN image_path IS NOT NULL
    AND image_path != '' THEN TRUE
    ELSE FALSE
END AS has_image,
image_path,

-- Engagement Metrics
GREATEST(COALESCE(views, 0), 0) AS views,
GREATEST(COALESCE(forwards, 0), 0) AS forwards,
GREATEST(COALESCE(reactions, 0), 0) AS reactions,
COALESCE(views, 0) + COALESCE(forwards, 0) + COALESCE(reactions, 0) AS total_engagement,

-- Data Quality Flags (FIXED: no alias reuse)
CASE
    WHEN LENGTH(
        TRIM(COALESCE(message_text, ''))
    ) = 0 THEN FALSE
    WHEN message_date > CURRENT_DATE THEN FALSE
    WHEN LENGTH(
        TRIM(COALESCE(message_text, ''))
    ) > 5000 THEN FALSE
    ELSE TRUE
END AS is_valid_message,

-- Metadata


loaded_at,
    CURRENT_TIMESTAMP AS transformed_at

  FROM source_data
)

SELECT * FROM cleaned_data