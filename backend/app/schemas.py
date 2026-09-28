from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import CompetitorStatus, ReelStatus, ShootStatus


class CompetitorRead(BaseModel):
    id: UUID
    username: str
    full_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    posts_count: int
    followers_count: int
    following_count: int
    reels_count: int = 0
    tracked: bool = False
    status: CompetitorStatus
    last_error: Optional[str] = None
    last_scraped_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ReelListItem(BaseModel):
    id: UUID
    competitor_id: UUID
    title: str
    author: str
    duration: str
    thumbnail_url: Optional[str] = None
    instagram_url: Optional[str] = None
    overlay_text: Optional[str] = None
    views_count: int
    likes_count: int
    comments_count: int
    has_transcript: bool = False
    status: ReelStatus
    posted_at: Optional[datetime] = None
    in_plan: bool = False
    plan_item_id: Optional[UUID] = None
    shoot_status: Optional[ShootStatus] = None


class ReelDetail(BaseModel):
    id: UUID
    competitor_id: UUID
    title: str
    caption: Optional[str] = None
    author: str
    author_name: Optional[str] = None
    avatar_url: Optional[str] = None
    duration: str
    duration_seconds: int
    views_count: int
    likes_count: int
    comments_count: int
    shares_count: int
    instagram_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    video_url: Optional[str] = None
    overlay_text: Optional[str] = None
    overview: str = ""
    hook: str
    script: str
    cta: str
    transcript: Optional[str] = None
    speech_pending: bool = False
    analysis_pending: bool = False
    why_it_works: Optional[str] = None
    posted_at: Optional[datetime] = None
    status: ReelStatus
    updated_at: datetime


class CompetitorLoadRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    force_refresh: bool = False


class CompetitorLoadResponse(BaseModel):
    competitor: CompetitorRead
    reels: list[ReelListItem]
    source: Literal["seed", "free", "cache"]
    message: str


class ReelUpdateRequest(BaseModel):
    section: Literal["hook", "script", "cta"]
    value: str = Field(min_length=1, max_length=2000)


class HealthResponse(BaseModel):
    status: str
    database: str
    ingest: str


class ContentPlanCreateRequest(BaseModel):
    reel_id: UUID


class ContentPlanUpdateRequest(BaseModel):
    shoot_status: ShootStatus


class ContentPlanItemRead(BaseModel):
    id: UUID
    reel_id: UUID
    shoot_status: ShootStatus
    title: str
    author: str
    duration: str
    thumbnail_url: Optional[str] = None
    instagram_url: Optional[str] = None
    overlay_text: Optional[str] = None
    views_count: int
    likes_count: int
    comments_count: int
    hook: str = ""
    script: str = ""
    cta: str = ""
    posted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
