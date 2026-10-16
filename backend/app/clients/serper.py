"""Client Serper.dev (API Google) — repli quand SearXNG est rate-limité.

API : POST https://google.serper.dev/search, en-tête `X-API-KEY`, corps JSON
`{"q", "num", "tbs"}`. `tbs=qdr:d|w|m|y` filtre la fraîcheur (mêmes paliers que
SearXNG). Retourne la MÊME forme que `searxng.search` pour le pipeline :
{title, url, snippet, source, publishedDate, img_src}.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Palier de fraîcheur SearXNG -> paramètre `tbs` Serper.
_TBS = {"day": "qdr:d", "week": "qdr:w", "month": "qdr:m", "year": "qdr:y"}


def _domain(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def enabled() -> bool:
    return bool(settings.serper_api_key)


async def get_balance(client: httpx.AsyncClient) -> Optional[dict[str, Any]]:
    """Solde de credits Serper restant (endpoint /account). None si indisponible.

    Retourne ex. {"balance": 2483, "rateLimit": 5}. Les credits Serper sont un
    stock unique (non renouvelable) : 1 recherche = 1 credit.
    """
    if not settings.serper_api_key:
        return None
    account_url = settings.serper_url.rsplit("/", 1)[0] + "/account"
    try:
        resp = await client.get(
            account_url,
            headers={"X-API-KEY": settings.serper_api_key},
            timeout=settings.serper_timeout,
        )
        if resp.status_code != 200:
            logger.warning("Serper /account %s", resp.status_code)
            return None
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Serper /account erreur: %s", exc)
        return None


async def search(
    client: httpx.AsyncClient,
    query: str,
    *,
    max_results: int = 15,
    time_range: Optional[str] = None,
) -> list[dict[str, Any]]:
    if not settings.serper_api_key:
        return []
    body: dict[str, Any] = {"q": query, "num": max_results}
    tbs = _TBS.get(time_range or "")
    if tbs:
        body["tbs"] = tbs
    try:
        resp = await client.post(
            settings.serper_url,
            headers={
                "X-API-KEY": settings.serper_api_key,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=settings.serper_timeout,
        )
        if resp.status_code != 200:
            logger.warning("Serper %s pour %r", resp.status_code, query)
            return []
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Serper erreur pour %r: %s", query, exc)
        return []

    out: list[dict[str, Any]] = []
    for r in data.get("organic", []) or []:
        url = r.get("link")
        if not url:
            continue
        out.append(
            {
                "title": r.get("title", "") or "",
                "url": url,
                "snippet": r.get("snippet", "") or "",
                "source": _domain(url),
                # Serper renvoie une date relative ("2 days ago") ou absente :
                # le pipeline la garde telle quelle (filtre tolérant si non ISO).
                "publishedDate": r.get("date"),
                "img_src": r.get("image"),
            }
        )
        if len(out) >= max_results:
            break
    return out
