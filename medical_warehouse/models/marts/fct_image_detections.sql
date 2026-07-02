-- =========================================================================
-- FACT TABLE: Image Detections
-- =========================================================================
--
-- PURPOSE:
--   Stores YOLO object detection results enriched with message engagement,
--   channel, and date dimensions for analytics.
--
-- GRAIN:
--   One row per analyzed image.
--
-- SOURCE:
--   stg_image_detections
--
-- DIMENSIONS:
--   - dim_channels
--   - dim_dates
--
-- RELATED FACT:
--   - fct_messages
--
-- =========================================================================


{{
    config(
        materialized='table',

        tags=[
            'marts',
            'fact',
            'image_detection',
            'production'
        ],

        meta={
            'owner': 'analytics_team',
            'layer': 'mart',
            'description': 'Fact table containing image detection results enriched with message engagement.'
        }
    )
}}


WITH image_detections AS (

    SELECT *

    FROM {{ ref('stg_image_detections') }}

),

messages AS (

    SELECT *

    FROM {{ ref('fct_messages') }}

),

final AS (

    SELECT

---------------------------------------------------------------------
-- Surrogate Key
---------------------------------------------------------------------

ROW_NUMBER() OVER (
    ORDER BY id.message_id, id.processed_at
) AS image_detection_key,

---------------------------------------------------------------------
-- Business Key
---------------------------------------------------------------------

id.message_id,

---------------------------------------------------------------------
-- Dimension Keys
---------------------------------------------------------------------

msg.channel_key, msg.date_key,

---------------------------------------------------------------------
-- Image Attributes
---------------------------------------------------------------------

id.channel_name,
id.image_path,
id.image_category,
id.detected_objects,
id.has_detections,
id.is_promotional,
id.is_product_display,

---------------------------------------------------------------------
-- Detection Metrics
---------------------------------------------------------------------

id.detection_count,

---------------------------------------------------------------------
-- Engagement Metrics
---------------------------------------------------------------------

COALESCE(msg.views, 0) AS views,
COALESCE(msg.forwards, 0) AS forwards,
COALESCE(msg.reactions, 0) AS reactions,
COALESCE(msg.total_engagement, 0) AS total_engagement,
msg.engagement_level,

---------------------------------------------------------------------
-- Analytical Flags
---------------------------------------------------------------------

CASE
    WHEN id.detection_count > 0 THEN TRUE
    ELSE FALSE
END AS detected_objects_flag,
CASE
    WHEN id.image_category = 'promotional'
    AND msg.total_engagement > 0 THEN TRUE
    ELSE FALSE
END AS promotional_with_engagement,
CASE
    WHEN id.image_category = 'product_display'
    AND id.detection_count > 0 THEN TRUE
    ELSE FALSE
END AS detected_product_display,

---------------------------------------------------------------------
-- Audit Columns
---------------------------------------------------------------------

id.processed_at,

        id.loaded_at,

        CURRENT_TIMESTAMP AS fact_created_at

    FROM image_detections id

    LEFT JOIN messages msg
        ON id.message_id = msg.message_id

)

SELECT * FROM final