from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Text, UniqueConstraint, func
from sqlmodel import Field, Relationship, SQLModel


class CompetitorStatus(str, Enum):
    pending = "pending"
    loading = "loading"
    ready = "ready"
    error = "error"


class ReelStatus(str, Enum):
    pending = "pending"
    ready = "ready"
    error = "error"


class Competitor(SQLModel, table=True):
    __tablename__ = "competitors"
    __table_args__ = (UniqueConstraint("username", name="uq_competitors_username"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    username: str = Field(index=True, max_length=100)
    full_name: Optional[str] = Field(default=None, max_length=200)
    bio: Optional[str] = Field(default=None, sa_column=Column(Text))
    avatar_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    posts_count: int = Field(default=0)
    followers_count: int = Field(default=0)
    following_count: int = Field(default=0)
    status: CompetitorStatus = Field(default=CompetitorStatus.pending)
    last_error: Optional[str] = Field(default=None, sa_column=Column(Text))
    apify_run_id: Optional[str] = Field(default=None, max_length=100)
    last_scraped_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        )
    )

    reels: list["Reel"] = Relationship(back_populates="competitor")


class Reel(SQLModel, table=True):
    __tablename__ = "reels"
    __table_args__ = (UniqueConstraint("external_id", name="uq_reels_external_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    competitor_id: UUID = Field(foreign_key="competitors.id", index=True)
    external_id: Optional[str] = Field(default=None, max_length=200, index=True)
    title: str = Field(max_length=300)
    caption: Optional[str] = Field(default=None, sa_column=Column(Text))
    instagram_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    thumbnail_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    video_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    duration_seconds: int = Field(default=0)
    views_count: int = Field(default=0)
    likes_count: int = Field(default=0)
    comments_count: int = Field(default=0)
    shares_count: int = Field(default=0)
    overlay_text: Optional[str] = Field(default=None, max_length=200)
    hook: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    script: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    cta: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    transcript: Optional[str] = Field(default=None, sa_column=Column(Text))
    analysis_overview: Optional[str] = Field(default=None, sa_column=Column(Text))
    why_it_works: Optional[str] = Field(default=None, sa_column=Column(Text))
    posted_at: Optional[datetime] = Field(default=None)
    status: ReelStatus = Field(default=ReelStatus.ready)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        )
    )

    competitor: Optional[Competitor] = Relationship(back_populates="reels")
