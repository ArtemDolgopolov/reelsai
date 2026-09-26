"""Proxy Instagram CDN media so browser thumbnails don't break on hotlink rules."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter(prefix="/media", tags=["media"])

ALLOWED_HOST_MARKERS = (
    "cdninstagram.com",
    "fbcdn.net",
    "instagram.com",
    "cdninstagram",
    "scontent",
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


@router.get("/proxy")
async def proxy_media(url: str = Query(..., min_length=12, max_length=4000)) -> Response:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise HTTPException(status_code=400, detail="Invalid media URL")
    if not any(marker in host for marker in ALLOWED_HOST_MARKERS):
        raise HTTPException(status_code=400, detail="Host is not allowed")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=25.0) as client:
            upstream = await client.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                    "Referer": "https://www.instagram.com/",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Media fetch failed: {exc}") from exc

    if upstream.status_code != 200 or not upstream.content:
        raise HTTPException(status_code=502, detail=f"Upstream returned HTTP {upstream.status_code}")

    content_type = upstream.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    if not content_type.startswith("image/") and "octet-stream" not in content_type:
        # Some CDN edges return video stills as octet-stream; still allow.
        if len(upstream.content) < 100:
            raise HTTPException(status_code=502, detail="Upstream did not return an image")

    return Response(
        content=upstream.content,
        media_type=content_type if content_type.startswith("image/") else "image/jpeg",
        headers={
            "Cache-Control": "public, max-age=86400",
        },
    )
