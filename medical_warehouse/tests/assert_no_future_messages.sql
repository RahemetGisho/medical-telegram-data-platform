-- assert_no_future_messages.sql
-- =========================================================================
-- CUSTOM DATA QUALITY TEST: No Future Messages
-- =========================================================================
--
-- PURPOSE:
--   Ensures no messages have timestamps in the future. This enforces a key
--   business rule that messages cannot be posted in the future.
--
-- BUSINESS RULE:
--   A message's posting date must be <= CURRENT_DATE + 1 day (allowing for
--   timezone differences and API delays)
--
-- TEST LOGIC:
--   Returns all messages with invalid future dates
--   Test PASSES if 0 rows are returned
--   Test FAILS if any future-dated messages exist
--
-- THRESHOLD:
--   CURRENT_DATE + INTERVAL '1 day' allows 1-day buffer for:
--   - Timezone handling
--   - API processing delays
--   - Data pipeline lag
--
-- IMPACT IF FAILED:
--   - Critical: Indicates broken data collection
--   - Action: Investigate scraper timezone handling
--   - Fix: Normalize all timestamps to UTC in staging
--
-- RELATED COLUMNS:
--   - message_date: Raw timestamp from Telegram
--   - fact_created_at: When record was created in warehouse
--
-- =========================================================================

SELECT 
    message_sk,
    message_id,
    channel_key,
    message_date,
    CURRENT_DATE AS current_date,
    (CURRENT_DATE + INTERVAL '1 day') AS threshold_date
FROM {{ ref('fct_messages') }}
WHERE message_date > CURRENT_DATE + INTERVAL '1 day'
ORDER BY message_date DESC