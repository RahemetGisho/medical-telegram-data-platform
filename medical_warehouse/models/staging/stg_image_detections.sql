-- =========================================================================
-- STAGING MODEL: Image Detections
-- =========================================================================
--
-- PURPOSE:
--   Cleans and standardizes YOLO image detection results loaded into the
--   processed schema.
--
-- GRAIN:
--   One row per analyzed image.
--
-- SOURCE:
--   processed.image_detections
--
-- =========================================================================

{{
    config(
        materialized='view',
        tags=['staging', 'image_detection']
    )
}}


WITH source_data AS (

    SELECT *

    FROM {{ source('processed', 'image_detections') }}

),

cleaned AS (

    SELECT

-- Business Key
CAST(message_id AS INTEGER) AS message_id,

-- Image Information
TRIM(image_path) AS image_path,
TRIM(channel_name) AS channel_name,
LOWER(TRIM(image_category)) AS image_category,

-- Detection Metrics
COALESCE(
    CAST(detection_count AS INTEGER),
    0
) AS detection_count,
NULLIF(TRIM(detected_objects), '') AS detected_objects,

-- Timestamps
CAST(processed_at AS TIMESTAMP) AS processed_at,
CAST(loaded_at AS TIMESTAMP) AS loaded_at,

-- Derived Fields
CASE
            WHEN COALESCE(detection_count, 0) > 0 THEN TRUE
            ELSE FALSE
        END AS has_detections,

        CASE
            WHEN LOWER(TRIM(image_category)) = 'promotional'
                THEN TRUE
            ELSE FALSE
        END AS is_promotional,

        CASE
            WHEN LOWER(TRIM(image_category)) = 'product_display'
                THEN TRUE
            ELSE FALSE
        END AS is_product_display,

        CURRENT_TIMESTAMP AS staged_at

    FROM source_data

)

SELECT * FROM cleaned