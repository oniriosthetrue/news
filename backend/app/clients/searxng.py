"""Client SearXNG (API JSON).

Prérequis : `formats: [html, json]` activé dans settings.yml (déjà le cas dans la
stack qwen). Retourne une liste de résultats {title, url, content, ...}.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def search(
    client: httpx.AsyncClient,
    query: str,
    *,
    max_results: int = 15,
    pageno: int = 1,
    time_range: Optional[str] = None,
) -> list[dict[str, Any]]:
    params = {
        "q": query,
        "format": "json",
        "language": settings.searxng_language,
        "pageno": pageno,
    }
    # time_range explicite (None -> réglage par défaut ; "" -> aucune limite).
    tr = settings.searxng_time_range if time_range is None else time_range
    if tr:
        params["time_range"] = tr
    try:
        resp = await client.get(
            settings.searxng_url, params=params, timeout=settings.http_timeout
        )
        if resp.status_code != 200:
            logger.warning("SearXNG %s pour %r", resp.status_code, query)
            return []
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("SearXNG erreur pour %r: %s", query, exc)
        return []

    results = data.get("results", []) or []
    out: list[dict[str, Any]] = []
    for r in results:
        url = r.get("url")
        if not url:
            continue
        out.append(
            {
                "title": r.get("title", "") or "",
                "url": url,
                "snippet": r.get("content", "") or "",
                "source": r.get("parsed_url", ["", "", ""])[1] if r.get("parsed_url") else "",
                "publishedDate": r.get("publishedDate"),
                "img_src": r.get("img_src"),
            }
        )
        if len(out) >= max_results:
            break
    return out
