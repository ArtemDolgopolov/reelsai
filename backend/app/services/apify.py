"""Apify integration stub.

When APIFY_TOKEN is set, load_competitor_reels will call the Apify actor.
Until then the API returns deterministic seed data so frontend and DB flow work end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings


@dataclass
class ApifyReelPayload:
    external_id: str
    title: str
    caption: str | None
    thumbnail_url: str | None
    video_url: str | None
    duration_seconds: int
    views_count: int
    overlay_text: str | None
    posted_at: str | None


@dataclass
class ApifyCompetitorPayload:
    username: str
    full_name: str | None
    bio: str | None
    avatar_url: str | None
    posts_count: int
    followers_count: int
    following_count: int
    reels: list[ApifyReelPayload]
    run_id: str | None = None


class ApifyNotConfiguredError(RuntimeError):
    pass


class ApifyClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.apify_token)

    async def fetch_competitor(self, username: str, limit: int = 20) -> ApifyCompetitorPayload:
        if not self.configured:
            raise ApifyNotConfiguredError(
                "APIFY_TOKEN is not configured. Add the token to enable live Instagram parsing."
            )

        # Placeholder for the next integration step with a real Apify actor run.
        # The shape below matches what the backend already expects to normalize into SQLModel.
        headers = {"Authorization": f"Bearer {self.settings.apify_token}"}
        actor_id = self.settings.apify_actor_id.replace("/", "~")
        payload = {
            "username": [username],
            "resultsLimit": limit,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"https://api.apify.com/v2/acts/{actor_id}/runs",
                headers=headers,
                json=payload,
                params={"waitForFinish": 120},
            )
            response.raise_for_status()
            run = response.json().get("data", {})
            dataset_id = run.get("defaultDatasetId")
            run_id = run.get("id")

            items_response = await client.get(
                f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                headers=headers,
                params={"format": "json"},
            )
            items_response.raise_for_status()
            items: list[dict[str, Any]] = items_response.json()

        reels: list[ApifyReelPayload] = []
        for item in items[:limit]:
            reels.append(
                ApifyReelPayload(
                    external_id=str(item.get("id") or item.get("shortCode") or item.get("url")),
                    title=(item.get("caption") or item.get("title") or "Instagram Reel")[:300],
                    caption=item.get("caption"),
                    thumbnail_url=item.get("displayUrl") or item.get("thumbnailUrl"),
                    video_url=item.get("videoUrl"),
                    duration_seconds=int(item.get("videoDuration") or 0),
                    views_count=int(item.get("videoViewCount") or item.get("playsCount") or 0),
                    overlay_text=None,
                    posted_at=item.get("timestamp"),
                )
            )

        profile = items[0] if items else {}
        owner = profile.get("ownerUsername") or username
        return ApifyCompetitorPayload(
            username=owner.lstrip("@"),
            full_name=profile.get("ownerFullName"),
            bio=None,
            avatar_url=profile.get("ownerProfilePicUrl"),
            posts_count=int(profile.get("ownerPostsCount") or len(reels)),
            followers_count=int(profile.get("ownerFollowersCount") or 0),
            following_count=int(profile.get("ownerFollowingCount") or 0),
            reels=reels,
            run_id=run_id,
        )
