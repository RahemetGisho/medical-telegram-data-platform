-- assert_positive_metrics.sql
-- =========================================================================
-- CUSTOM DATA QUALITY TEST: Positive Engagement Metrics
-- =========================================================================
--
-- PURPOSE:
--   Validates that all engagement metrics (views, forwards, reactions) are
--   non-negative. Negative metrics indicate data corruption or API errors.
--
-- BUSINESS RULE:
--   Engagement metrics must be >= 0:
--   • views >= 0
--   • forwards >= 0
--   • reactions >= 0
--   • total_engagement >= 0
--
-- TEST LOGIC:
--   Returns all messages with negative metrics
--   Test PASSES if 0 rows are returned
--   Test FAILS if any records have negative values
--
-- ROOT CAUSES OF FAILURES:
--   1. Telegram API returning corrupted data
--   2. Data transformation errors (type casting)
--   3. Arithmetic errors in derived metrics
--   4. Data pipeline bugs
--
-- IMPACT IF FAILED:
--   - High: Breaks all aggregation logic
--   - Distorts analytics and reports
--   - Action: Investigate data extraction layer
--   - Fix: Validate at source (scraper) or enforce in staging
--
-- REMEDIATION:
--   Use GREATEST(COALESCE(metric, 0), 0) in staging layer to enforce
--   non-negative constraint at transformation time.
--
-- MONITORING:
--   - Track number of anomalies by channel and date
--   - Alert if failures exceed 1% of messages
--   - Review raw data for systematic issues
--
-- =========================================================================

SELECT 
    message_sk,
    message_id,
    channel_key,
    views,
    forwards,
    reactions,
    total_engagement,
    CASE 
        WHEN views < 0 THEN 'views negative'
        WHEN forwards < 0 THEN 'forwards negative'
        WHEN reactions < 0 THEN 'reactions negative'
        WHEN total_engagement < 0 THEN 'total_engagement negative'
        ELSE 'unknown'
    END AS issue_type
FROM {{ ref('fct_messages') }}
WHERE views < 0 
   OR forwards < 0 
   OR reactions < 0 
   OR total_engagement < 0
ORDER BY message_sk