"""
Task 4: Analytical REST API
Exposes medical telegram warehouse through FastAPI endpoints.
Provides comprehensive analytics on products, channels, and engagement patterns.
"""

import re
from typing import List, Optional
from collections import Counter
from datetime import datetime
import logging

from fastapi import FastAPI, HTTPException, Query, status, Path
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api.database import db
from api.schemas import (
    ChannelResponse,
    MessageResponse,
    TopProductsResponse,
    ChannelActivityResponse,
    MessageSearchResponse,
    VisualContentStatsResponse,
    AnalyticsSummaryResponse,
    HealthCheckResponse,
)
from src.logging_config import setup_logger

# Initialize logger
logger = setup_logger("medical_warehouse.api")


# ===== LIFESPAN =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    logger.info("Starting Medical Telegram Warehouse API")
    if not db.connect():
        logger.error("Failed to connect to database on startup")

    yield

    logger.info("Shutting down API")
    db.disconnect()


# ===== FASTAPI APPLICATION =====
app = FastAPI(
    title="Medical Telegram Warehouse API",
    description="Analytical REST API exposing insights from medical Telegram channels",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware for browser requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Root"])
async def read_root():
    """
    Root endpoint serving as a welcome message and router link.
    """
    return {
        "status": "online",
        "message": "Welcome to the Medical Telegram Data Platform API",
        "documentation": "Navigate to /docs for interactive OpenAPI specifications",
    }


# ===== ERROR HANDLERS =====
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Handle validation errors."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Invalid parameter",
            "detail": str(exc),
            "timestamp": datetime.now().isoformat(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle unexpected errors."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred",
            "timestamp": datetime.now().isoformat(),
        },
    )


# ===== HEALTH CHECK ENDPOINT =====
@app.get(
    "/health",
    response_model=HealthCheckResponse,
    tags=["Health"],
    summary="Health Check",
    description="Verify API and database connectivity",
)
async def health_check():
    try:
        cursor = db.connection.cursor()
        cursor.execute("SELECT 1")
        cursor.close()

        return HealthCheckResponse(
            status="healthy",
            service="Medical Telegram Warehouse API",
            database="connected",
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.warning(f"Health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        )


# ===== CORE ENDPOINTS =====
@app.get(
    "/channels",
    response_model=List[ChannelResponse],
    tags=["Channels"],
    summary="List All Channels",
    description="Get all channels with aggregated statistics",
)
async def list_channels(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of channels"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    try:
        query = """
            SELECT 
                channel_key,
                channel_name,
                channel_type,
                total_messages,
                total_images,
                ROUND(avg_views::NUMERIC, 2) as avg_views,
                ROUND(avg_engagement::NUMERIC, 2) as avg_engagement,
                activity_status,
                first_post_date,
                last_post_date
            FROM marts.dim_channels
            ORDER BY total_messages DESC
            LIMIT %s OFFSET %s
        """
        results = db.execute_query(query, (limit, offset))

        if not results:
            logger.warning("No channels found")
            return []

        return [ChannelResponse(**dict(row)) for row in results]
    except Exception as e:
        logger.error(f"Error fetching channels: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch channels",
        )


@app.get(
    "/channels/{channel_name}",
    response_model=ChannelResponse,
    tags=["Channels"],
    summary="Get Channel Details",
    description="Get detailed statistics for a specific channel",
)
async def get_channel(channel_name: str = Path(..., description="Name of the channel")):
    try:
        query = """
            SELECT 
                channel_key,
                channel_name,
                channel_type,
                total_messages,
                total_images,
                ROUND(avg_views::NUMERIC, 2) as avg_views,
                ROUND(avg_engagement::NUMERIC, 2) as avg_engagement,
                activity_status,
                first_post_date,
                last_post_date
            FROM marts.dim_channels
            WHERE channel_name = %s
        """
        results = db.execute_query(query, (channel_name,))
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Channel '{channel_name}' not found",
            )
        return ChannelResponse(**dict(results[0]))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching channel {channel_name}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch channel details",
        )


@app.get(
    "/messages",
    response_model=List[MessageResponse],
    tags=["Messages"],
    summary="Search Messages",
    description="Search messages with optional filters",
)
async def search_messages(
    channel_name: Optional[str] = Query(None, description="Filter by channel name"),
    engagement_level: Optional[str] = Query(
        None, description="Filter by engagement level"
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    try:
        query = """
            SELECT 
                f.message_id,
                f.message_sk,
                d.channel_name,
                f.message_text,
                f.views,
                f.forwards,
                f.reactions,
                f.total_engagement,
                f.engagement_level,
                f.message_date
            FROM marts.fct_messages f
            JOIN marts.dim_channels d ON f.channel_key = d.channel_key
            WHERE 1=1
        """
        params = []
        if channel_name:
            query += " AND d.channel_name = %s"
            params.append(channel_name)
        if engagement_level:
            query += " AND f.engagement_level = %s"
            params.append(engagement_level)

        query += " ORDER BY f.total_engagement DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        results = db.execute_query(query, tuple(params))
        return [MessageResponse(**dict(row)) for row in results]
    except Exception as e:
        logger.error(f"Error searching messages: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search messages",
        )


# ===== TASK 4 SPECIFIC ENDPOINTS =====
@app.get(
    "/api/reports/top-products",
    response_model=TopProductsResponse,
    tags=["Reports"],
    summary="Top Products/Terms",
    description="Get most frequently mentioned products across channels",
)
async def get_top_products(
    limit: int = Query(10, ge=1, le=50, description="Number of products to return"),
    channel_name: Optional[str] = Query(None, description="Optional channel filter"),
):
    try:
        if channel_name:
            query = """
                SELECT f.message_text
                FROM marts.fct_messages f
                JOIN marts.dim_channels d ON f.channel_key = d.channel_key
                WHERE d.channel_name = %s AND f.message_text IS NOT NULL
                ORDER BY f.total_engagement DESC
            """
            results = db.execute_query(query, (channel_name,))
        else:
            query = """
                SELECT f.message_text
                FROM marts.fct_messages f
                WHERE f.message_text IS NOT NULL
                ORDER BY f.total_engagement DESC
            """
            results = db.execute_query(query)

        product_keywords = _extract_product_keywords(
            [r["message_text"] for r in results]
        )
        top_products = product_keywords.most_common(limit)

        logger.info(f"Extracted {len(top_products)} top products")
        return TopProductsResponse(
            limit=limit,
            channel_filter=channel_name,
            total_messages_analyzed=len(results),
            products=[
                {"product_name": prod, "mention_count": count}
                for prod, count in top_products
            ],
        )
    except Exception as e:
        logger.error(f"Error fetching top products: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch products",
        )


@app.get(
    "/api/channels/{channel_name}/activity",
    response_model=ChannelActivityResponse,
    tags=["Reports"],
    summary="Channel Activity Trends",
    description="Get posting activity and engagement trends for a channel",
)
async def get_channel_activity(
    channel_name: str = Path(..., description="Channel name"),
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
):
    try:
        query = """
            SELECT 
                dd.calendar_date,
                COUNT(f.message_sk) as daily_messages,
                ROUND(AVG(f.views)::NUMERIC, 2) as avg_views,
                SUM(f.views) as total_views,
                SUM(f.forwards) as total_forwards,
                SUM(f.reactions) as total_reactions,
                ROUND(AVG(f.total_engagement)::NUMERIC, 2) as avg_engagement
            FROM marts.fct_messages f
            JOIN marts.dim_channels d ON f.channel_key = d.channel_key
            JOIN marts.dim_dates dd ON f.date_key = dd.date_key
            WHERE d.channel_name = %s
                AND dd.calendar_date >= CURRENT_DATE - INTERVAL '%s day'
            GROUP BY dd.calendar_date
            ORDER BY dd.calendar_date DESC
        """
        results = db.execute_query(query, (channel_name, days))
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Channel '{channel_name}' not found or no activity",
            )

        return ChannelActivityResponse(
            channel_name=channel_name,
            period_days=days,
            activity_data=[
                {
                    "date": r["calendar_date"].isoformat(),
                    "daily_messages": r["daily_messages"],
                    "avg_views": float(r["avg_views"] or 0),
                    "total_views": r["total_views"] or 0,
                    "total_forwards": r["total_forwards"] or 0,
                    "total_reactions": r["total_reactions"] or 0,
                    "avg_engagement": float(r["avg_engagement"] or 0),
                }
                for r in results
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching channel activity: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch activity data",
        )


@app.get(
    "/api/search/messages",
    response_model=MessageSearchResponse,
    tags=["Search"],
    summary="Full-Text Message Search",
    description="Search messages by keyword with optional filters",
)
async def search_messages_by_keyword(
    query: str = Query(..., min_length=1, max_length=100, description="Search keyword"),
    limit: int = Query(20, ge=1, le=100, description="Result limit"),
    min_views: int = Query(0, ge=0, description="Minimum view count filter"),
    channel_name: Optional[str] = Query(None, description="Optional channel filter"),
):
    try:
        search_pattern = f"%{query}%"
        sql_query = """
            SELECT 
                f.message_id,
                d.channel_name,
                f.message_text,
                f.views,
                f.forwards,
                f.reactions,
                f.total_engagement,
                dd.calendar_date
            FROM marts.fct_messages f
            JOIN marts.dim_channels d ON f.channel_key = d.channel_key
            JOIN marts.dim_dates dd ON f.date_key = dd.date_key
            WHERE LOWER(f.message_text) LIKE LOWER(%s)
                AND f.views >= %s
        """
        params = [search_pattern, min_views]
        if channel_name:
            sql_query += " AND d.channel_name = %s"
            params.append(channel_name)

        sql_query += " ORDER BY f.total_engagement DESC LIMIT %s"
        params.append(limit)

        results = db.execute_query(sql_query, tuple(params))
        logger.info(f"Found {len(results)} messages matching '{query}'")

        return MessageSearchResponse(
            query=query,
            min_views=min_views,
            channel_filter=channel_name,
            total_results=len(results),
            messages=[
                {
                    "message_id": r["message_id"],
                    "channel": r["channel_name"],
                    "text": (
                        r["message_text"][:500] + "..."
                        if len(r["message_text"]) > 500
                        else r["message_text"]
                    ),
                    "views": r["views"],
                    "forwards": r["forwards"],
                    "reactions": r["reactions"],
                    "total_engagement": r["total_engagement"],
                    "date": r["calendar_date"].isoformat(),
                }
                for r in results
            ],
        )
    except Exception as e:
        logger.error(f"Error searching messages: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search messages",
        )


@app.get(
    "/api/reports/visual-content",
    response_model=VisualContentStatsResponse,
    tags=["Reports"],
    summary="Visual Content Statistics",
    description="Analyze image usage and effectiveness across channels",
)
async def get_visual_content_stats():
    try:
        query = """
            SELECT 
                d.channel_name,
                COUNT(f.message_sk) as total_messages,
                COUNT(CASE WHEN f.has_image THEN 1 END) as messages_with_images,
                ROUND(
                    COUNT(CASE WHEN f.has_image THEN 1 END)::NUMERIC / 
                    NULLIF(COUNT(f.message_sk), 0) * 100,
                    2
                ) as image_usage_ratio_pct,
                ROUND(AVG(f.views)::NUMERIC, 2) as avg_views_all,
                ROUND(
                    AVG(CASE WHEN f.has_image THEN f.views END)::NUMERIC, 2
                ) as avg_views_with_image,
                ROUND(
                    AVG(CASE WHEN NOT f.has_image THEN f.views END)::NUMERIC, 2
                ) as avg_views_without_image,
                ROUND(
                    AVG(CASE WHEN f.has_image THEN f.total_engagement END)::NUMERIC, 2
                ) as avg_engagement_with_image
            FROM marts.fct_messages f
            JOIN marts.dim_channels d ON f.channel_key = d.channel_key
            GROUP BY d.channel_name
            ORDER BY image_usage_ratio_pct DESC
        """
        results = db.execute_query(query)
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No data available"
            )

        return VisualContentStatsResponse(
            timestamp=datetime.now().isoformat(),
            channels=[
                {
                    "channel": r["channel_name"],
                    "total_messages": r["total_messages"],
                    "messages_with_images": r["messages_with_images"],
                    "image_usage_ratio_pct": float(r["image_usage_ratio_pct"]),
                    "avg_views_all": float(r["avg_views_all"] or 0),
                    "avg_views_with_image": float(r["avg_views_with_image"] or 0),
                    "avg_views_without_image": float(r["avg_views_without_image"] or 0),
                    "image_impact": (
                        "Positive"
                        if (
                            r["avg_views_with_image"]
                            and r["avg_views_without_image"]
                            and r["avg_views_with_image"] > r["avg_views_without_image"]
                        )
                        else "Neutral"
                    ),
                }
                for r in results
            ],
        )
    except Exception as e:
        logger.error(f"Error fetching visual stats: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch visual content statistics",
        )


# ===== ANALYTICS SUMMARY ENDPOINT =====
@app.get(
    "/analytics/summary",
    response_model=AnalyticsSummaryResponse,
    tags=["Analytics"],
    summary="Platform Summary",
    description="Overall platform statistics and metrics",
)
async def get_analytics_summary():
    try:
        query = """
            SELECT 
                (SELECT COUNT(*) FROM marts.fct_messages) as total_messages,
                (SELECT COUNT(DISTINCT channel_key) FROM marts.fct_messages) as unique_channels,
                (SELECT COUNT(*) FROM marts.fct_messages WHERE has_image) as messages_with_images,
                (SELECT ROUND(AVG(views)::NUMERIC, 2) FROM marts.fct_messages) as avg_views,
                (SELECT SUM(views) FROM marts.fct_messages) as total_views,
                (SELECT MAX(message_date) FROM marts.fct_messages) as latest_message_date,
                (SELECT ROUND(AVG(total_engagement)::NUMERIC, 2) FROM marts.fct_messages) as avg_engagement,
                (SELECT COUNT(DISTINCT message_date::DATE) FROM marts.fct_messages) as active_days
        """
        results = db.execute_query(query)
        row = results[0] if results else {}

        return AnalyticsSummaryResponse(
            total_messages=row.get("total_messages", 0),
            unique_channels=row.get("unique_channels", 0),
            messages_with_images=row.get("messages_with_images", 0),
            avg_views=float(row.get("avg_views", 0) or 0),
            total_views=row.get("total_views", 0),
            avg_engagement=float(row.get("avg_engagement", 0) or 0),
            active_days=row.get("active_days", 0),
            latest_message_date=(
                row.get("latest_message_date").isoformat()
                if row.get("latest_message_date")
                else None
            ),
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"Error fetching summary: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch summary",
        )


# ===== UTILITY FUNCTIONS =====
def _extract_product_keywords(messages: List[str]) -> Counter:
    product_keywords = {
        "paracetamol",
        "ibuprofen",
        "aspirin",
        "vitamin",
        "tablet",
        "capsule",
        "cream",
        "ointment",
        "lotion",
        "serum",
        "gel",
        "shampoo",
        "conditioner",
        "moisturizer",
        "sunscreen",
        "medicine",
        "drug",
        "pharmaceutical",
        "supplement",
        "antibiotic",
        "antiseptic",
        "disinfectant",
        "powder",
        "spray",
        "oil",
        "balm",
        "tonic",
        "syrup",
    }
    products_found = Counter()
    for message in messages:
        if not message:
            continue
        text_lower = message.lower()
        for product in product_keywords:
            if product in text_lower:
                products_found[product] += 1

        quantity_pattern = (
            r"(\d+(?:\.\d+)?)\s*(mg|g|ml|l|%|tablets?|pieces?|boxes?|packs?)"
        )
        for match in re.finditer(quantity_pattern, text_lower):
            quantity_term = f"{match.group(1)}{match.group(2)}"
            products_found[quantity_term] += 1

    return products_found


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info"
    )
