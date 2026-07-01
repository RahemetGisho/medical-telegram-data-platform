-- assert_engagement_level_accuracy.sql
-- =========================================================================
-- CUSTOM DATA QUALITY TEST: Engagement Level Classification Accuracy
-- =========================================================================
--
-- PURPOSE:
--   Validates that engagement_level classification accurately reflects the
--   actual total_engagement metric. Ensures analytics are based on correct
--   categorizations.
--
-- BUSINESS RULE:
--   Engagement level thresholds (based on views primarily):
--   • 'No Engagement': views = 0 AND forwards = 0 AND reactions = 0
--   • 'Low Engagement': views < 10
--   • 'Medium Engagement': views >= 10 AND views < 50
--   • 'High Engagement': views >= 50 AND views < 200
--   • 'Viral': views >= 200
--
-- TEST LOGIC:
--   Validates engagement_level matches the ranges above
--   Returns all misclassified messages
--   Test PASSES if 0 rows (classifications accurate)
--   Test FAILS if thresholds violated
--
-- IMPACT IF FAILED:
--   - High: Directly affects analytics and insights
--   - Misrepresents viral/trending content
--   - Marketing decisions based on wrong categories
--   - Action: Investigate staging layer thresholds
--   - Fix: Align classification logic with business rules
--
-- ROOT CAUSES:
--   1. Incorrect threshold values in CASE statement
--   2. Logic errors with AND/OR conditions
--   3. Integer vs. numeric type issues
--   4. Missing edge cases (exactly 10, exactly 50, etc.)
--
-- REMEDIATION:
--   1. Review exact threshold values
--   2. Test boundary conditions (10, 50, 200)
--   3. Verify numeric precision in calculations
--   4. Document threshold decisions
--
-- EXAMPLES OF MISCLASSIFICATION:
--   Bad: views = 5 but engagement_level = 'Medium'
--   Bad: views = 150 but engagement_level = 'Low'
--   Bad: views = 0 but engagement_level = 'No Engagement' when forwards > 0
--
-- BUSINESS IMPLICATIONS:
--   • 'Viral' messages are marketing opportunities
--   • Wrong classification → Missed opportunities
--   • Could affect pricing/promotion strategies
--   • Important for trend analysis and insights
--
-- MONITORING:
--   - Check distribution of engagement levels
--   - Alert if viral content rate drops unexpectedly
--   - Monitor threshold boundary cases
--   - Track classification accuracy over time
--
-- THRESHOLD DEFINITION:
--   These thresholds should be reviewed periodically:
--   • May vary by channel (Medical vs. Cosmetics)
--   • May need adjustment as audience grows
--   • Consider seasonal patterns
--   • Document any threshold changes in git
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
    engagement_level,
    CASE 
        WHEN engagement_level = 'No Engagement' 
            AND (views > 0 OR forwards > 0 OR reactions > 0)
            THEN 'Error: No Engagement but has metrics'
        
        WHEN engagement_level = 'Low Engagement' 
            AND (views >= 10 OR (views = 0 AND (forwards > 0 OR reactions > 0)))
            THEN 'Error: Low Engagement threshold violated'
        
        WHEN engagement_level = 'Medium Engagement' 
            AND (views < 10 OR views >= 50)
            THEN 'Error: Medium Engagement outside range [10, 50)'
        
        WHEN engagement_level = 'High Engagement' 
            AND (views < 50 OR views >= 200)
            THEN 'Error: High Engagement outside range [50, 200)'
        
        WHEN engagement_level = 'Viral' 
            AND views < 200
            THEN 'Error: Viral but views < 200'
        
        ELSE 'Unknown classification error'
    END AS issue_description
FROM {{ ref('fct_messages') }}
WHERE 
    -- No Engagement: must have 0 for all metrics
    (engagement_level = 'No Engagement' 
        AND (views > 0 OR forwards > 0 OR reactions > 0))

-- Low Engagement: 0 to 9 views
OR (
    engagement_level = 'Low Engagement'
    AND (
        views >= 10
        OR (
            views = 0
            AND (
                forwards > 0
                OR reactions > 0
            )
        )
    )
)

-- Medium Engagement: 10 to 49 views
OR (
    engagement_level = 'Medium Engagement'
    AND (
        views < 10
        OR views >= 50
    )
)

-- High Engagement: 50 to 199 views
OR (
    engagement_level = 'High Engagement'
    AND (
        views < 50
        OR views >= 200
    )
)

-- Viral: 200+ views
OR (
    engagement_level = 'Viral'
    AND views < 200
)
ORDER BY views DESC