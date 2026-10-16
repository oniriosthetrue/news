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


def _news_url() -> str:
    """Endpoint Google News de Serper (index dedie actualites, plus riche que
    la recherche web generique et renvoie de vraies dates)."""
    return settings.serper_url.replace("/search", "/news")


async def search(
    client: httpx.AsyncClient,
    query: str,
    *,
    max_results: int = 15,
    time_range: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Index Google News (endpoint /news). Retourne la forme du pipeline."""
    if not settings.serper_api_key:
        return []
    body: dict[str, Any] = {"q": query, "num": max_results}
    # L'index /news ne gere pas fiablement tbs=qdr:w|m|y (renvoie 0). On
    # n'applique qdr:d que pour le palier jour ; la fenetre exacte est de toute
    # facon re-filtree par le pipeline apres scraping (date reelle de l'article).
    if (time_range or "") == "day":
        body["tbs"] = "qdr:d"
    try:
        resp = await client.post(
            _news_url(),
            headers={
                "X-API-KEY": settings.serper_api_key,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=settings.serper_timeout,
        )
        if resp.status_code != 200:
            logger.warning("Serper /news %s pour %r", resp.status_code, query)
            return []
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Serper /news erreur pour %r: %s", query, exc)
        return []

    out: list[dict[str, Any]] = []
    for r in data.get("news", []) or []:
        url = r.get("link")
        if not url:
            continue
        out.append(
            {
                "title": r.get("title", "") or "",
                "url": url,
                "snippet": r.get("snippet", "") or "",
                "source": r.get("source") or _domain(url),
                # L'index News renvoie une date exploitable par le pipeline.
                "publishedDate": r.get("date"),
                "img_src": r.get("image"),
            }
        )
        if len(out) >= max_results:
            break
    return out
