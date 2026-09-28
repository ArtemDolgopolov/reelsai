"""Helpers to scope competitors / plans to the signed-in user."""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session, col, select

from app.models import Competitor, User, UserCompetitorTrack


def tracked_competitor_ids(session: Session, user_id: UUID) -> list[UUID]:
    return list(
        session.exec(
            select(UserCompetitorTrack.competitor_id).where(
                UserCompetitorTrack.user_id == user_id
            )
        ).all()
    )


def user_tracks_competitor(session: Session, user_id: UUID, competitor_id: UUID) -> bool:
    row = session.exec(
        select(UserCompetitorTrack.id).where(
            UserCompetitorTrack.user_id == user_id,
            UserCompetitorTrack.competitor_id == competitor_id,
        )
    ).first()
    return row is not None


def ensure_user_tracks_competitor(
    session: Session,
    user: User,
    competitor: Competitor,
) -> UserCompetitorTrack:
    existing = session.exec(
        select(UserCompetitorTrack).where(
            UserCompetitorTrack.user_id == user.id,
            UserCompetitorTrack.competitor_id == competitor.id,
        )
    ).first()
    if existing:
        return existing
    track = UserCompetitorTrack(user_id=user.id, competitor_id=competitor.id)
    session.add(track)
    competitor.tracked = True
    session.add(competitor)
    session.commit()
    session.refresh(track)
    return track


def list_tracked_competitors(session: Session, user_id: UUID) -> list[Competitor]:
    return list(
        session.exec(
            select(Competitor)
            .join(
                UserCompetitorTrack,
                col(UserCompetitorTrack.competitor_id) == Competitor.id,
            )
            .where(UserCompetitorTrack.user_id == user_id)
            .order_by(col(Competitor.updated_at).desc())
        ).all()
    )
