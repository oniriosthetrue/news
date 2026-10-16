"""Client GNews (gnews.io) — repli quand SearXNG est rate-limité.

API : GET https://gnews.io/api/v4/search, param `apikey`. `from` (ISO UTC)
filtre la fraîcheur. Retourne la MÊME forme que `searxng.search` pour le
pipeline : {title, url, snippet, source, publishedDate, img_src}.

Plan gratuit : ~100 req/jour, 10 articles max par requête (`max` plafonné).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Palier de fraîcheur SearXNG -> nombre de jours en arrière pour `from`.
_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}
# GNews plan gratuit : 10 articles max par appel.
_MAX_PER_REQ = 10


def enabled() -> bool:
    return bool(settings.gnews_api_key)


def _since_iso(bucket: Optional[str]) -> Optional[str]:
    days = _DAYS.get(bucket or "")
    if not days:
        return None
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


async def search(
    client: httpx.AsyncClient,
    query: str,
    *,
    max_results: int = 15,
    time_range: Optional[str] = None,
) -> list[dict[str, Any]]:
    if not settings.gnews_api_key:
        return []
    params: dict[str, Any] = {
        "q": query,
        "lang": "fr",
        "max": min(max_results, _MAX_PER_REQ),
        "apikey": settings.gnews_api_key,
    }
    since = _since_iso(time_range)
    if since:
        params["from"] = since
    try:
        resp = await client.get(
            settings.gnews_url,
            params=params,
            timeout=settings.gnews_timeout,
        )
        if resp.status_code != 200:
            logger.warning(
                "GNews %s pour %r: %s", resp.status_code, query, resp.text[:200]
            )
            return []
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("GNews erreur pour %r: %s", query, exc)
        return []

    out: list[dict[str, Any]] = []
    for r in data.get("articles", []) or []:
        url = r.get("url")
        if not url:
            continue
        source = (r.get("source") or {}).get("name") or ""
        out.append(
            {
                "title": r.get("title", "") or "",
                "url": url,
                "snippet": r.get("description", "") or "",
                "source": source,
                "publishedDate": r.get("publishedAt"),
                "img_src": r.get("image"),
            }
        )
        if len(out) >= max_results:
            break
    return out
