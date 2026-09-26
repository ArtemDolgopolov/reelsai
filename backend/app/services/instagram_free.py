"""Free Instagram reel ingestion via yt-dlp + public web endpoints.

No Apify. Profile listing uses Instagram's public web API; per-reel audio
is extracted with yt-dlp and transcribed locally with faster-whisper.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
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
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


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


def _browser_headers(username: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-IG-App-ID": IG_APP_ID,
        "X-ASBD-ID": "129477",
        "X-Requested-With": "XMLHttpRequest",
    }
    if username:
        headers["Referer"] = f"https://www.instagram.com/{username}/"
    return headers


def _caption_from_node(node: dict[str, Any]) -> str | None:
    edges = (
        node.get("edge_media_to_caption", {}).get("edges")
        or node.get("edge_media_to_caption", {}).get("edges")
        or []
    )
    if edges:
        text = edges[0].get("node", {}).get("text")
        if text:
            return text
    return node.get("caption") or node.get("accessibility_caption")


def _ytdlp_json(url: str, extra_args: list[str] | None = None) -> dict[str, Any]:
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--no-playlist",
        "-J",
        "--no-warnings",
        *(extra_args or []),
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0:
        raise InstagramFreeError(
            f"yt-dlp failed for {url}: {(result.stderr or result.stdout or 'unknown error')[:400]}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise InstagramFreeError(f"yt-dlp returned invalid JSON for {url}") from exc


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
        "-o",
        outtmpl,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    if result.returncode != 0:
        logger.warning("Audio download failed for %s: %s", url, (result.stderr or "")[:300])
        return None
    candidates = sorted(workdir.glob("audio.*"))
    return candidates[0] if candidates else None


def _normalize_reel_url(url: str) -> str:
    match = re.search(r"instagram\.com/(?:reel|p|tv)/([^/?#]+)", url)
    if match:
        return f"https://www.instagram.com/reel/{match.group(1)}/"
    return url


def _download_audio_from_direct(url: str, workdir: Path) -> Path | None:
    """Fallback when yt-dlp is rate-limited but we still have a CDN media URL."""
    target = workdir / "direct.mp4"
    try:
        with httpx.Client(follow_redirects=True, timeout=120.0, headers={"User-Agent": USER_AGENT}) as client:
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
        timeout=120,
        check=False,
    )
    if result.returncode != 0 or not wav.exists():
        logger.warning("ffmpeg extract failed: %s", (result.stderr or "")[:300])
        return None
    return wav


def enrich_reel_from_url(
    url: str,
    *,
    transcribe: bool = True,
    existing: FreeReelPayload | None = None,
) -> FreeReelPayload:
    """Fetch metadata (and optional speech transcript) for a single reel URL."""
    webpage = _normalize_reel_url(url)
    info: dict[str, Any] = {}
    try:
        info = _ytdlp_json(webpage)
    except InstagramFreeError as exc:
        logger.warning("yt-dlp metadata failed for %s: %s", webpage, exc)
        if existing is None:
            raise

    shortcode = str(info.get("id") or info.get("display_id") or (existing.external_id if existing else "") or "")
    caption = info.get("description") or (existing.caption if existing else None)
    title = (caption or info.get("title") or (existing.title if existing else None) or "Instagram Reel").strip()[:300]
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
            audio_path = _download_audio(webpage, workdir)
            if audio_path is None and video_url:
                audio_path = _download_audio_from_direct(video_url, workdir)
            if audio_path is not None:
                spoken = transcribe_audio_file(audio_path)
                if spoken:
                    transcript = spoken

    return FreeReelPayload(
        external_id=shortcode or (existing.external_id if existing else webpage),
        title=title,
        caption=caption or (existing.caption if existing else None),
        transcript=transcript,
        instagram_url=webpage,
        thumbnail_url=thumbnail,
        video_url=None,
        duration_seconds=duration,
        views_count=views,
        likes_count=likes,
        comments_count=comments,
        shares_count=0,
        overlay_text=None,
        posted_at=posted_at,
    )


def _fetch_profile_user(username: str) -> dict[str, Any]:
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    with httpx.Client(headers=_browser_headers(username), follow_redirects=True, timeout=45.0) as client:
        response = client.get(url)
        if response.status_code == 429:
            raise InstagramFreeError(
                "Instagram временно ограничил запросы (429). Подождите несколько минут и попробуйте снова."
            )
        if response.status_code != 200:
            raise InstagramFreeError(
                f"Не удалось получить профиль @{username}: HTTP {response.status_code}"
            )
        payload = response.json()
    user = payload.get("data", {}).get("user")
    if not user:
        raise InstagramFreeError(f"Профиль @{username} не найден или закрыт")
    return user


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


def _payload_from_node(node: dict[str, Any], username: str) -> FreeReelPayload:
    shortcode = str(node.get("shortcode") or node.get("code") or "")
    caption = _caption_from_node(node)
    title = (caption or "Instagram Reel").strip()[:300]
    return FreeReelPayload(
        external_id=shortcode,
        title=title,
        caption=caption,
        transcript=None,
        instagram_url=f"https://www.instagram.com/reel/{shortcode}/" if shortcode else None,
        thumbnail_url=node.get("display_url") or node.get("thumbnail_src"),
        video_url=node.get("video_url"),
        duration_seconds=int(node.get("video_duration") or 0),
        views_count=int(node.get("video_view_count") or node.get("video_play_count") or 0),
        likes_count=int(
            (node.get("edge_liked_by") or {}).get("count")
            or (node.get("edge_media_preview_like") or {}).get("count")
            or 0
        ),
        comments_count=int((node.get("edge_media_to_comment") or {}).get("count") or 0),
        shares_count=0,
        overlay_text=None,
        posted_at=_parse_timestamp(node.get("taken_at_timestamp")),
    )


class InstagramFreeClient:
    def fetch_competitor(
        self,
        username: str,
        limit: int = 20,
        *,
        transcribe: bool = True,
    ) -> FreeCompetitorPayload:
        username = username.lstrip("@").lower()
        user = _fetch_profile_user(username)
        nodes = _nodes_from_profile(user, limit=max(limit * 2, limit))
        if not nodes:
            raise InstagramFreeError(
                f"У @{username} не нашлось публичных видео/рилсов через бесплатный парсер"
            )

        reels: list[FreeReelPayload] = []
        for node in nodes:
            base = _payload_from_node(node, username)
            if not base.instagram_url:
                continue
            try:
                enriched = enrich_reel_from_url(
                    base.instagram_url,
                    transcribe=transcribe,
                    existing=base,
                )
                # Prefer richer profile counters when yt-dlp omits them.
                if not enriched.views_count:
                    enriched.views_count = base.views_count
                if not enriched.likes_count:
                    enriched.likes_count = base.likes_count
                if not enriched.comments_count:
                    enriched.comments_count = base.comments_count
                if not enriched.duration_seconds:
                    enriched.duration_seconds = base.duration_seconds
                if not enriched.thumbnail_url:
                    enriched.thumbnail_url = base.thumbnail_url
                reels.append(enriched)
            except Exception as exc:  # noqa: BLE001 - keep loading other reels
                logger.warning("Skipping reel %s: %s", base.instagram_url, exc)
                reels.append(base)
            if len(reels) >= limit:
                break

        if not reels:
            raise InstagramFreeError(f"Не удалось загрузить рилсы @{username}")

        return FreeCompetitorPayload(
            username=username,
            full_name=user.get("full_name"),
            bio=user.get("biography"),
            avatar_url=user.get("profile_pic_url_hd") or user.get("profile_pic_url"),
            posts_count=int(user.get("edge_owner_to_timeline_media", {}).get("count") or len(reels)),
            followers_count=int(user.get("edge_followed_by", {}).get("count") or 0),
            following_count=int(user.get("edge_follow", {}).get("count") or 0),
            reels=reels,
        )

    def refresh_transcripts(
        self,
        items: list[tuple[str, FreeReelPayload | None]],
        *,
        only_missing: bool = True,
    ) -> list[FreeReelPayload]:
        """Re-download audio and transcribe existing reel URLs."""
        updated: list[FreeReelPayload] = []
        for url, existing in items:
            if not url:
                continue
            has_speech = bool(existing and existing.transcript and len(existing.transcript.strip()) >= 40)
            if only_missing and has_speech:
                if existing:
                    updated.append(existing)
                continue
            try:
                updated.append(enrich_reel_from_url(url, transcribe=True, existing=existing))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Transcript refresh failed for %s: %s", url, exc)
                if existing:
                    updated.append(existing)
        return updated


def looks_like_real_transcript(text: str | None) -> bool:
    if not text:
        return False
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) < 40:
        return False
    # Apify sometimes returned tiny caption-like stubs.
    if cleaned.count(" ") < 4 and len(cleaned) < 80:
        return False
    return True
