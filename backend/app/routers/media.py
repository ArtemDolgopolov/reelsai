"""Proxy Instagram CDN media so browser thumbnails/video don't break on hotlink rules."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

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


def _validate_media_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise HTTPException(status_code=400, detail="Invalid media URL")
    if not any(marker in host for marker in ALLOWED_HOST_MARKERS):
        raise HTTPException(status_code=400, detail="Host is not allowed")


@router.get("/proxy")
async def proxy_media(url: str = Query(..., min_length=12, max_length=4000)) -> Response:
    _validate_media_url(url)

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
        if len(upstream.content) < 100:
            raise HTTPException(status_code=502, detail="Upstream did not return an image")

    return Response(
        content=upstream.content,
        media_type=content_type if content_type.startswith("image/") else "image/jpeg",
        headers={
            "Cache-Control": "public, max-age=86400",
        },
    )


@router.get("/video")
async def proxy_video(
    request: Request,
    url: str = Query(..., min_length=12, max_length=4000),
) -> StreamingResponse:
    """Stream Instagram CDN video for in-app preview (supports Range for seeking)."""
    _validate_media_url(url)

    upstream_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Referer": "https://www.instagram.com/",
    }
    range_header = request.headers.get("range")
    if range_header:
        upstream_headers["Range"] = range_header

    client = httpx.AsyncClient(follow_redirects=True, timeout=60.0)
    try:
        req = client.build_request("GET", url, headers=upstream_headers)
        upstream = await client.send(req, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Video fetch failed: {exc}") from exc

    if upstream.status_code not in {200, 206}:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Upstream returned HTTP {upstream.status_code}")

    media_type = (upstream.headers.get("content-type") or "video/mp4").split(";")[0].strip()
    if not media_type.startswith("video/") and "octet-stream" not in media_type:
        media_type = "video/mp4"

    out_headers: dict[str, str] = {
        "Cache-Control": "private, max-age=600",
        "Accept-Ranges": upstream.headers.get("accept-ranges", "bytes"),
    }
    if "content-length" in upstream.headers:
        out_headers["Content-Length"] = upstream.headers["content-length"]
    if "content-range" in upstream.headers:
        out_headers["Content-Range"] = upstream.headers["content-range"]

    async def body():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        media_type=media_type,
        headers=out_headers,
    )
