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


class ShootStatus(str, Enum):
    todo = "todo"  # not started
    ready = "ready"  # script ready, waiting to film
    done = "done"  # filmed and published


class UserStatus(str, Enum):
    pending_verification = "pending_verification"
    active = "active"
    disabled = "disabled"


class AuthChallengePurpose(str, Enum):
    register = "register"
    login_2fa = "login_2fa"
    password_reset = "password_reset"


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
    tracked: bool = Field(default=False, index=True)
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


class ContentPlanItem(SQLModel, table=True):
    __tablename__ = "content_plan_items"
    __table_args__ = (
        UniqueConstraint("user_id", "reel_id", name="uq_content_plan_user_reel"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    reel_id: UUID = Field(foreign_key="reels.id", index=True)
    shoot_status: ShootStatus = Field(default=ShootStatus.todo, index=True)
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


class UserCompetitorTrack(SQLModel, table=True):
    """Per-user saved competitors. Scraped Competitor/Reel rows stay shared cache."""

    __tablename__ = "user_competitor_tracks"
    __table_args__ = (
        UniqueConstraint("user_id", "competitor_id", name="uq_user_competitor_track"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    competitor_id: UUID = Field(foreign_key="competitors.id", index=True)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, max_length=320)
    password_hash: Optional[str] = Field(default=None, max_length=255)
    name: Optional[str] = Field(default=None, max_length=120)
    username: Optional[str] = Field(default=None, max_length=80, index=True)
    status: UserStatus = Field(default=UserStatus.pending_verification, index=True)
    email_verified_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    last_login_at: Optional[datetime] = Field(
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


class AuthChallenge(SQLModel, table=True):
    __tablename__ = "auth_challenges"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    purpose: AuthChallengePurpose = Field(index=True)
    code_hash: str = Field(max_length=128)
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    attempts: int = Field(default=0)
    max_attempts: int = Field(default=5)
    consumed_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    ip: Optional[str] = Field(default=None, max_length=64)
    user_agent: Optional[str] = Field(default=None, max_length=400)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class AuthSession(SQLModel, table=True):
    __tablename__ = "auth_sessions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    refresh_token_hash: str = Field(max_length=128, index=True)
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    revoked_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    ip: Optional[str] = Field(default=None, max_length=64)
    user_agent: Optional[str] = Field(default=None, max_length=400)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class OAuthAccount(SQLModel, table=True):
    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    provider: str = Field(max_length=32, index=True)
    provider_user_id: str = Field(max_length=255)
    email: Optional[str] = Field(default=None, max_length=320)
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
