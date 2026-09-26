"""Apify integration stub.

When APIFY_TOKEN is set, load_competitor_reels will call the Apify actor.
Until then the API returns deterministic seed data so frontend and DB flow work end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings


@dataclass
class ApifyReelPayload:
    external_id: str
    title: str
    caption: str | None
    transcript: str | None
    instagram_url: str | None
    thumbnail_url: str | None
    video_url: str | None
    duration_seconds: int
    views_count: int
    likes_count: int
    comments_count: int
    shares_count: int
    overlay_text: str | None
    posted_at: datetime | None


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

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            return None

    async def fetch_competitor(self, username: str, limit: int = 20) -> ApifyCompetitorPayload:
        if not self.configured:
            raise ApifyNotConfiguredError(
                "APIFY_TOKEN is not configured. Add the token to enable live Instagram parsing."
            )

        # Placeholder for the next integration step with a real Apify actor run.
        # The shape below matches what the backend already expects to normalize into SQLModel.
        headers = {"Authorization": f"Bearer {self.settings.apify_token}"}
        actor_id = self.settings.apify_actor_id.replace("/", "~")
        # Actor sometimes returns tagged/collaborator reels mixed in. Fetch extra,
        # then keep only items owned by the requested username.
        fetch_limit = max(limit * 3, 40)
        payload = {
            "username": [username],
            "resultsLimit": fetch_limit,
            "skipPinnedPosts": True,
            "includeTranscript": True,
            "includeDownloadedVideo": False,
            "includeSharesCount": False,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
            response = await client.post(
                f"https://api.apify.com/v2/acts/{actor_id}/runs",
                headers=headers,
                json=payload,
                params={"waitForFinish": 120},
            )
            response.raise_for_status()
            run = response.json().get("data", {})
            run_id = run.get("id")
            run_status = run.get("status")
            for _ in range(3):
                if run_status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
                    break
                run_response = await client.get(
                    f"https://api.apify.com/v2/actor-runs/{run_id}",
                    headers=headers,
                    params={"waitForFinish": 60},
                )
                run_response.raise_for_status()
                run = run_response.json().get("data", {})
                run_status = run.get("status")

            if run_status != "SUCCEEDED":
                raise RuntimeError(f"Apify run {run_id} finished with status {run_status}")
            dataset_id = run.get("defaultDatasetId")
            if not dataset_id:
                raise RuntimeError(f"Apify run {run_id} returned no dataset")

            items_response = await client.get(
                f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                headers=headers,
                params={"format": "json"},
            )
            items_response.raise_for_status()
            items: list[dict[str, Any]] = items_response.json()

        return self._build_payload(username=username, items=items, limit=limit, run_id=run_id)

    async def fetch_competitor_from_run(
        self, username: str, run_id: str, limit: int = 20
    ) -> ApifyCompetitorPayload:
        """Reuse an existing Apify run/dataset without spending new credits."""
        if not self.configured:
            raise ApifyNotConfiguredError(
                "APIFY_TOKEN is not configured. Add the token to enable live Instagram parsing."
            )

        headers = {"Authorization": f"Bearer {self.settings.apify_token}"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            run_response = await client.get(
                f"https://api.apify.com/v2/actor-runs/{run_id}",
                headers=headers,
            )
            run_response.raise_for_status()
            run = run_response.json().get("data", {})
            if run.get("status") != "SUCCEEDED":
                raise RuntimeError(f"Apify run {run_id} finished with status {run.get('status')}")
            dataset_id = run.get("defaultDatasetId")
            if not dataset_id:
                raise RuntimeError(f"Apify run {run_id} returned no dataset")

            items_response = await client.get(
                f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                headers=headers,
                params={"format": "json"},
            )
            items_response.raise_for_status()
            items: list[dict[str, Any]] = items_response.json()

        return self._build_payload(username=username, items=items, limit=limit, run_id=run_id)

    def _build_payload(
        self,
        username: str,
        items: list[dict[str, Any]],
        limit: int,
        run_id: str | None,
    ) -> ApifyCompetitorPayload:
        wanted = username.lstrip("@").lower()
        owned = [
            item
            for item in items
            if (item.get("ownerUsername") or wanted).lstrip("@").lower() == wanted
        ]
        owned.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
        selected = owned[:limit]

        reels: list[ApifyReelPayload] = []
        for item in selected:
            reels.append(
                ApifyReelPayload(
                    external_id=str(item.get("id") or item.get("shortCode") or item.get("url")),
                    title=(item.get("caption") or item.get("title") or "Instagram Reel")[:300],
                    caption=item.get("caption"),
                    transcript=item.get("transcript"),
                    instagram_url=item.get("url") or item.get("inputUrl"),
                    thumbnail_url=item.get("displayUrl") or item.get("thumbnailUrl"),
                    video_url=item.get("videoUrl"),
                    duration_seconds=int(item.get("videoDuration") or 0),
                    views_count=int(
                        item.get("videoViewCount")
                        or item.get("videoPlayCount")
                        or item.get("playsCount")
                        or 0
                    ),
                    likes_count=int(item.get("likesCount") or 0),
                    comments_count=int(item.get("commentsCount") or 0),
                    shares_count=int(item.get("sharesCount") or 0),
                    overlay_text=None,
                    posted_at=self._parse_timestamp(item.get("timestamp")),
                )
            )

        profile = selected[0] if selected else (owned[0] if owned else {})
        return ApifyCompetitorPayload(
            username=wanted,
            full_name=profile.get("ownerFullName"),
            bio=None,
            avatar_url=profile.get("ownerProfilePicUrl") or profile.get("displayUrl"),
            posts_count=int(profile.get("ownerPostsCount") or len(reels)),
            followers_count=int(profile.get("ownerFollowersCount") or 0),
            following_count=int(profile.get("ownerFollowingCount") or 0),
            reels=reels,
            run_id=run_id,
        )
