"""Free Instagram reel ingestion — metadata fast path + optional audio STT.

Uses Instagram's public web API with a primed guest session (no Apify).
Speech transcripts run in the background so competitor load stays fast.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.services.transcribe import transcribe_audio_file

logger = logging.getLogger(__name__)

IG_APP_ID = "936619743392459"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = httpx.Timeout(12.0, connect=6.0)


@dataclass
class FreeReelPayload:
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
class FreeCompetitorPayload:
    username: str
    full_name: str | None
    bio: str | None
    avatar_url: str | None
    posts_count: int
    followers_count: int
    following_count: int
    reels: list[FreeReelPayload] = field(default_factory=list)


class InstagramFreeError(RuntimeError):
    pass


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            return None
    return None


def _browser_headers(username: str | None = None, csrf: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-IG-App-ID": IG_APP_ID,
        "X-ASBD-ID": "129477",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "sec-ch-ua": '"Chromium";v="126", "Not.A/Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }
    if username:
        headers["Referer"] = f"https://www.instagram.com/{username}/"
        headers["Origin"] = "https://www.instagram.com"
    if csrf:
        headers["X-CSRFToken"] = csrf
    return headers


def _caption_from_node(node: dict[str, Any]) -> str | None:
    edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
    if edges:
        text = edges[0].get("node", {}).get("text")
        if text:
            return text
    caption = node.get("caption")
    if isinstance(caption, dict):
        return caption.get("text")
    if isinstance(caption, str):
        return caption
    return node.get("accessibility_caption")


def looks_like_real_transcript(text: str | None) -> bool:
    if not text:
        return False
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) < 40:
        return False
    if cleaned.count(" ") < 4 and len(cleaned) < 80:
        return False
    return True


def _normalize_reel_url(url: str) -> str:
    match = re.search(r"instagram\.com/(?:reel|p|tv)/([^/?#]+)", url)
    if match:
        return f"https://www.instagram.com/reel/{match.group(1)}/"
    return url


def _prime_guest_client(username: str | None = None) -> httpx.Client:
    client = httpx.Client(
        headers=_browser_headers(username),
        follow_redirects=True,
        timeout=REQUEST_TIMEOUT,
    )
    try:
        home = client.get("https://www.instagram.com/")
        csrf = client.cookies.get("csrftoken")
        if not csrf:
            csrf = uuid.uuid4().hex
            client.cookies.set("csrftoken", csrf, domain=".instagram.com")
        client.headers.update(_browser_headers(username, csrf=csrf))
        if username:
            client.get(f"https://www.instagram.com/{username}/")
        _ = home.status_code
    except Exception as exc:  # noqa: BLE001
        logger.warning("Guest session prime failed: %s", exc)
    return client


def _fetch_web_profile(client: httpx.Client, username: str) -> dict[str, Any] | None:
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    response = client.get(url)
    if response.status_code in {429, 401, 403}:
        logger.info("web_profile_info HTTP %s for @%s", response.status_code, username)
        return None
    if response.status_code != 200:
        logger.info("web_profile_info HTTP %s for @%s", response.status_code, username)
        return None
    return response.json().get("data", {}).get("user")


def _fetch_user_feed(
    client: httpx.Client, username: str, count: int = 24
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Primary free path — stays up when web_profile_info is rate-limited."""
    url = f"https://www.instagram.com/api/v1/feed/user/{username}/username/"
    items: list[dict[str, Any]] = []
    user: dict[str, Any] | None = None
    max_id: str | None = None

    while len(items) < count:
        params: dict[str, Any] = {"count": min(12, count - len(items))}
        if max_id:
            params["max_id"] = max_id
        response = client.get(url, params=params)
        if response.status_code == 429:
            if items:
                break
            raise InstagramFreeError("rate_limited")
        if response.status_code != 200:
            logger.info("user feed HTTP %s for @%s", response.status_code, username)
            break
        payload = response.json()
        batch = payload.get("items") or []
        if user is None:
            user = payload.get("user")
        if not batch:
            break
        items.extend(item for item in batch if isinstance(item, dict))
        if not payload.get("more_available"):
            break
        max_id = payload.get("next_max_id")
        if not max_id:
            break

    return items[:count], user


def _fetch_clips(client: httpx.Client, user_id: str, count: int = 20) -> list[dict[str, Any]]:
    response = client.post(
        "https://www.instagram.com/api/v1/clips/user/",
        data={
            "target_user_id": user_id,
            "page_size": str(count),
            "include_feed_video": "true",
        },
    )
    if response.status_code != 200:
        logger.info("clips/user HTTP %s for user_id=%s", response.status_code, user_id)
        return []
    nodes: list[dict[str, Any]] = []
    for item in response.json().get("items") or []:
        media = item.get("media") if isinstance(item, dict) else None
        if isinstance(media, dict):
            nodes.append(media)
    return nodes


def _nodes_from_profile(user: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    edges = user.get("edge_owner_to_timeline_media", {}).get("edges") or []
    nodes: list[dict[str, Any]] = []
    for edge in edges:
        node = edge.get("node") or {}
        if not node.get("is_video"):
            continue
        nodes.append(node)
        if len(nodes) >= limit:
            break
    return nodes


def _payload_from_node(node: dict[str, Any]) -> FreeReelPayload | None:
    shortcode = str(node.get("code") or node.get("shortcode") or "")
    if not shortcode:
        return None

    media_type = node.get("media_type")
    product = node.get("product_type")
    has_video = bool(
        node.get("is_video")
        or node.get("video_versions")
        or node.get("video_url")
        or media_type in {2, "2"}
        or product in {"clips", "reel", "reels", "igtv"}
    )
    if not has_video:
        return None

    caption = _caption_from_node(node)
    title = (caption or "Instagram Reel").strip()[:300]
    video_versions = node.get("video_versions") or []
    video_url = node.get("video_url")
    if not video_url and video_versions:
        video_url = video_versions[0].get("url")

    likes = (
        (node.get("edge_liked_by") or {}).get("count")
        or (node.get("edge_media_preview_like") or {}).get("count")
        or node.get("like_count")
        or 0
    )
    comments = (
        (node.get("edge_media_to_comment") or {}).get("count")
        or node.get("comment_count")
        or 0
    )
    views = (
        node.get("play_count")
        or node.get("video_view_count")
        or node.get("video_play_count")
        or node.get("view_count")
        or 0
    )
    taken = node.get("taken_at_timestamp") or node.get("taken_at") or node.get("device_timestamp")
    image = node.get("display_url") or node.get("thumbnail_src") or node.get("display_uri")
    candidates = (node.get("image_versions2") or {}).get("candidates") or []
    if candidates:
        # Prefer a mid/large still (~640px+) over the tiniest candidate.
        ranked = sorted(
            (c for c in candidates if c.get("url")),
            key=lambda c: abs(int(c.get("width") or 0) - 640),
        )
        if ranked:
            image = ranked[0].get("url") or image
    if not image:
        resources = node.get("carousel_media") or []
        for resource in resources:
            nested = (resource.get("image_versions2") or {}).get("candidates") or []
            if nested and nested[0].get("url"):
                image = nested[0]["url"]
                break

    return FreeReelPayload(
        external_id=shortcode,
        title=title,
        caption=caption,
        transcript=None,
        instagram_url=f"https://www.instagram.com/reel/{shortcode}/",
        thumbnail_url=image,
        video_url=video_url,
        duration_seconds=int(node.get("video_duration") or 0),
        views_count=int(views or 0),
        likes_count=int(likes or 0),
        comments_count=int(comments or 0),
        shares_count=0,
        overlay_text=None,
        posted_at=_parse_timestamp(taken),
    )


def _ytdlp_json(url: str) -> dict[str, Any]:
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--no-playlist",
        "-J",
        "--no-warnings",
        "--socket-timeout",
        "15",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=False)
    if result.returncode != 0:
        raise InstagramFreeError(
            f"yt-dlp failed for {url}: {(result.stderr or result.stdout or 'unknown error')[:300]}"
        )
    return json.loads(result.stdout)


def _download_audio(url: str, workdir: Path) -> Path | None:
    outtmpl = str(workdir / "audio.%(ext)s")
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format",
        "wav",
        "--audio-quality",
        "0",
        "--no-playlist",
        "--no-warnings",
        "--socket-timeout",
        "20",
        "-o",
        outtmpl,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=False)
    if result.returncode != 0:
        logger.warning("Audio download failed for %s: %s", url, (result.stderr or "")[:200])
        return None
    candidates = sorted(workdir.glob("audio.*"))
    return candidates[0] if candidates else None


def _download_audio_from_direct(url: str, workdir: Path) -> Path | None:
    target = workdir / "direct.mp4"
    try:
        with httpx.Client(follow_redirects=True, timeout=60.0, headers={"User-Agent": USER_AGENT}) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                with target.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Direct media download failed: %s", exc)
        return None

    wav = workdir / "audio.wav"
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(target),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(wav),
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if result.returncode != 0 or not wav.exists():
        logger.warning("ffmpeg extract failed: %s", (result.stderr or "")[:200])
        return None
    return wav


def enrich_reel_from_url(
    url: str,
    *,
    transcribe: bool = True,
    existing: FreeReelPayload | None = None,
) -> FreeReelPayload:
    webpage = _normalize_reel_url(url)
    info: dict[str, Any] = {}
    # Prefer already-known feed metadata + CDN URL. Avoid yt-dlp unless we have nothing else —
    # Instagram heavily rate-limits datacenter IPs on single-reel downloads.
    if existing is None or not (existing.video_url or existing.caption or existing.views_count):
        try:
            info = _ytdlp_json(webpage)
        except Exception as exc:  # noqa: BLE001
            logger.warning("yt-dlp metadata failed for %s: %s", webpage, exc)
            if existing is None:
                raise InstagramFreeError(str(exc)) from exc

    shortcode = str(
        info.get("id")
        or info.get("display_id")
        or (existing.external_id if existing else "")
        or ""
    )
    caption = info.get("description") or (existing.caption if existing else None)
    title = (
        caption or info.get("title") or (existing.title if existing else None) or "Instagram Reel"
    ).strip()[:300]
    duration = int(info.get("duration") or (existing.duration_seconds if existing else 0) or 0)
    views = int(
        info.get("view_count")
        or info.get("play_count")
        or (existing.views_count if existing else 0)
        or 0
    )
    likes = int(info.get("like_count") or (existing.likes_count if existing else 0) or 0)
    comments = int(info.get("comment_count") or (existing.comments_count if existing else 0) or 0)
    thumbnail = info.get("thumbnail") or (existing.thumbnail_url if existing else None)
    webpage = info.get("webpage_url") or webpage
    posted_at = _parse_timestamp(info.get("timestamp")) or (existing.posted_at if existing else None)
    video_url = existing.video_url if existing else None

    transcript = existing.transcript if existing else None
    if transcribe and not looks_like_real_transcript(transcript):
        with tempfile.TemporaryDirectory(prefix="reelsai-audio-") as tmp:
            workdir = Path(tmp)
            audio_path = None
            if video_url:
                audio_path = _download_audio_from_direct(video_url, workdir)
            if audio_path is None:
                audio_path = _download_audio(webpage, workdir)
            if audio_path is not None:
                spoken = transcribe_audio_file(
                    audio_path,
                    hint_text=caption or title,
                )
                if spoken:
                    transcript = spoken

    return FreeReelPayload(
        external_id=shortcode or (existing.external_id if existing else webpage),
        title=title,
        caption=caption or (existing.caption if existing else None),
        transcript=transcript,
        instagram_url=webpage,
        thumbnail_url=thumbnail,
        video_url=video_url,
        duration_seconds=duration,
        views_count=views,
        likes_count=likes,
        comments_count=comments,
        shares_count=0,
        overlay_text=None,
        posted_at=posted_at,
    )


class InstagramFreeClient:
    def fetch_competitor_metadata(self, username: str, limit: int = 20) -> FreeCompetitorPayload:
        """Fast path: profile + reel cards only. No audio / STT."""
        username = username.lstrip("@").lower()
        last_error = "unknown"

        for attempt in range(2):
            client = _prime_guest_client(username)
            try:
                # Feed-by-username first — works even when web_profile_info returns 429.
                feed_items, feed_user = _fetch_user_feed(client, username, count=max(limit, 12))
                web_user = _fetch_web_profile(client, username)

                user: dict[str, Any] | None = None
                if web_user:
                    user = {
                        "full_name": web_user.get("full_name"),
                        "biography": web_user.get("biography"),
                        "profile_pic_url": web_user.get("profile_pic_url"),
                        "profile_pic_url_hd": web_user.get("profile_pic_url_hd"),
                        "edge_owner_to_timeline_media": web_user.get("edge_owner_to_timeline_media")
                        or {"count": len(feed_items)},
                        "edge_followed_by": web_user.get("edge_followed_by") or {"count": 0},
                        "edge_follow": web_user.get("edge_follow") or {"count": 0},
                        "id": web_user.get("id") or web_user.get("pk"),
                    }
                elif feed_user:
                    user = {
                        "full_name": feed_user.get("full_name"),
                        "biography": None,
                        "profile_pic_url": feed_user.get("profile_pic_url"),
                        "profile_pic_url_hd": feed_user.get("profile_pic_url"),
                        "edge_owner_to_timeline_media": {"count": len(feed_items)},
                        "edge_followed_by": {"count": 0},
                        "edge_follow": {"count": 0},
                        "id": feed_user.get("id") or feed_user.get("pk"),
                    }

                clip_items: list[dict[str, Any]] = []
                user_id = str((user or {}).get("id") or "")
                if user_id:
                    try:
                        clip_items = _fetch_clips(client, user_id, count=limit)
                    except Exception as exc:  # noqa: BLE001
                        logger.info("clips fetch skipped: %s", exc)

                timeline_nodes = _nodes_from_profile(web_user, limit=limit * 2) if web_user else []

                nodes: list[dict[str, Any]] = []
                seen: set[str] = set()
                for node in feed_items + clip_items + timeline_nodes:
                    code = str(node.get("code") or node.get("shortcode") or "")
                    if not code or code in seen:
                        continue
                    seen.add(code)
                    nodes.append(node)
                    if len(nodes) >= limit:
                        break

                if not nodes:
                    raise InstagramFreeError(f"У @{username} не нашлось публичных рилсов")
                if not user:
                    owner = nodes[0].get("user") or {}
                    user = {
                        "full_name": owner.get("full_name"),
                        "biography": None,
                        "profile_pic_url": owner.get("profile_pic_url"),
                        "profile_pic_url_hd": owner.get("profile_pic_url"),
                        "edge_owner_to_timeline_media": {"count": len(nodes)},
                        "edge_followed_by": {"count": 0},
                        "edge_follow": {"count": 0},
                    }

                reels: list[FreeReelPayload] = []
                for node in nodes:
                    payload = _payload_from_node(node)
                    if payload:
                        reels.append(payload)
                    if len(reels) >= limit:
                        break

                if not reels:
                    raise InstagramFreeError(f"Не удалось разобрать рилсы @{username}")

                return FreeCompetitorPayload(
                    username=username,
                    full_name=user.get("full_name"),
                    bio=user.get("biography"),
                    avatar_url=user.get("profile_pic_url_hd") or user.get("profile_pic_url"),
                    posts_count=int(
                        (user.get("edge_owner_to_timeline_media") or {}).get("count") or len(reels)
                    ),
                    followers_count=int((user.get("edge_followed_by") or {}).get("count") or 0),
                    following_count=int((user.get("edge_follow") or {}).get("count") or 0),
                    reels=reels,
                )
            except InstagramFreeError as exc:
                last_error = str(exc)
                if last_error == "rate_limited" and attempt == 0:
                    time.sleep(1.2)
                    continue
                if last_error == "rate_limited":
                    raise InstagramFreeError(
                        "Instagram временно ограничил запросы (429). "
                        "Подождите пару минут — уже сохранённые конкуренты открываются из кэша."
                    ) from exc
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                logger.warning("Metadata fetch attempt %s failed: %s", attempt + 1, exc)
                if attempt == 0:
                    time.sleep(0.8)
                    continue
                raise InstagramFreeError(f"Не удалось загрузить @{username}: {last_error}") from exc
            finally:
                client.close()

        raise InstagramFreeError(f"Не удалось загрузить @{username}: {last_error}")

    def refresh_transcripts(
        self,
        items: list[tuple[str, FreeReelPayload | None]],
        *,
        only_missing: bool = True,
        max_items: int = 8,
    ) -> list[FreeReelPayload]:
        updated: list[FreeReelPayload] = []
        processed = 0
        for url, existing in items:
            if not url:
                continue
            has_speech = bool(
                existing and existing.transcript and looks_like_real_transcript(existing.transcript)
            )
            if only_missing and has_speech:
                if existing:
                    updated.append(existing)
                continue
            if processed >= max_items:
                if existing:
                    updated.append(existing)
                continue
            try:
                updated.append(enrich_reel_from_url(url, transcribe=True, existing=existing))
                processed += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Transcript refresh failed for %s: %s", url, exc)
                if existing:
                    updated.append(existing)
        return updated
