"""Client NewsAPI (newsapi.org) — repli quand SearXNG est rate-limité.

API : GET https://newsapi.org/v2/everything, param `apiKey`. `from` (ISO UTC)
filtre la fraîcheur. Retourne la MÊME forme que `searxng.search` pour le
pipeline : {title, url, snippet, source, publishedDate, img_src}.

Plan gratuit "Developer" : ~100 req/jour, articles différés (~24 h). On ne
l'appelle que si SearXNG revient vide, pour économiser le quota.
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


def enabled() -> bool:
    return bool(settings.newsapi_api_key)


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
    if not settings.newsapi_api_key:
        return []
    params: dict[str, Any] = {
        "q": query,
        "pageSize": max_results,
        "sortBy": "publishedAt",
        "language": "fr",
        "apiKey": settings.newsapi_api_key,
    }
    since = _since_iso(time_range)
    if since:
        params["from"] = since
    try:
        resp = await client.get(
            settings.newsapi_url,
            params=params,
            timeout=settings.newsapi_timeout,
        )
        if resp.status_code != 200:
            logger.warning(
                "NewsAPI %s pour %r: %s", resp.status_code, query, resp.text[:200]
            )
            return []
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("NewsAPI erreur pour %r: %s", query, exc)
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
                "img_src": r.get("urlToImage"),
            }
        )
        if len(out) >= max_results:
            break
    return out
