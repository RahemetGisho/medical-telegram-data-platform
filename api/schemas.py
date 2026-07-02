"""
Pydantic data validation schemas defining API request and response shapes.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class HealthCheckResponse(BaseModel):
    status: str
    service: str
    database: str
    timestamp: str


class ErrorResponse(BaseModel):
    error: str
    detail: str
    timestamp: str


class ChannelResponse(BaseModel):
    channel_key: int
    channel_name: str
    channel_type: str
    total_messages: int
    total_images: int
    avg_views: float
    avg_engagement: float
    activity_status: str
    first_post_date: Optional[Any] = None
    last_post_date: Optional[Any] = None


class MessageResponse(BaseModel):
    message_id: int
    message_sk: int
    channel_name: str
    message_text: Optional[str] = None
    views: Optional[int] = 0
    forwards: Optional[int] = 0
    reactions: Optional[int] = 0
    total_engagement: Optional[int] = 0
    engagement_level: Optional[str] = None
    message_date: Optional[Any] = None


class ProductDetail(BaseModel):
    product_name: str
    mention_count: int


class TopProductsResponse(BaseModel):
    limit: int
    channel_filter: Optional[str] = None
    total_messages_analyzed: int
    products: List[ProductDetail]


class DailyActivity(BaseModel):
    date: str
    daily_messages: int
    avg_views: float
    total_views: int
    total_forwards: int
    total_reactions: int
    avg_engagement: float


class ChannelActivityResponse(BaseModel):
    channel_name: str
    period_days: int
    activity_data: List[DailyActivity]


class SearchMessageDetail(BaseModel):
    message_id: int
    channel: str
    text: Optional[str] = None
    views: Optional[int] = 0
    forwards: Optional[int] = 0
    reactions: Optional[int] = 0
    total_engagement: Optional[int] = 0
    date: str


class MessageSearchResponse(BaseModel):
    query: str
    min_views: int
    channel_filter: Optional[str] = None
    total_results: int
    messages: List[SearchMessageDetail]


class VisualChannelStats(BaseModel):
    channel: str
    total_messages: int
    messages_with_images: int
    image_usage_ratio_pct: float
    avg_views_all: float
    avg_views_with_image: float
    avg_views_without_image: float
    image_impact: str


class VisualContentStatsResponse(BaseModel):
    timestamp: str
    channels: List[VisualChannelStats]


class AnalyticsSummaryResponse(BaseModel):
    total_messages: int
    unique_channels: int
    messages_with_images: int
    avg_views: float
    total_views: int
    avg_engagement: float
    active_days: int
    latest_message_date: Optional[str] = None
    timestamp: str


class EngagementMetrics(BaseModel):
    views: int
    forwards: int
    reactions: int
    total_engagement: int
