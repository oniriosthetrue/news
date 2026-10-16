"""Recherche unifiee : SearXNG puis replis sur API a cle, en FUSION.

SearXNG est gratuit mais rate-limite (moteurs suspendus -> liste vide). Pour
maximiser le nombre d'articles (et se rapprocher de la richesse de Google
News), on ne s'arrete plus a la premiere source non vide : on interroge
TOUTES les sources actives et on fusionne leurs resultats (union dedupliquee
par URL). SearXNG n'est interroge que s'il est active.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from ..config import get_settings
from . import gnews, newsapi, searxng, serper

logger = logging.getLogger(__name__)
settings = get_settings()

# Sources ordonnees : (nom, module). Toutes les sources actives sont interrogees
# puis fusionnees. NewsAPI/GNews : quota renouvelable ~100 req/j ; Serper (index
# Google News) : stock de credits unique -> appele en dernier mais systematiquement.
_SOURCES = (("SearXNG", searxng), ("NewsAPI", newsapi), ("GNews", gnews), ("Serper", serper))


async def search(
    client: httpx.AsyncClient,
    query: str,
    *,
    max_results: int = 15,
    time_range: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Interroge toutes les sources actives et fusionne leurs resultats."""
    merged: dict[str, dict[str, Any]] = {}
    for name, mod in _SOURCES:
        if name == "SearXNG" and not settings.searxng_enabled:
            continue
        if not mod.enabled():
            continue
        try:
            results = await mod.search(
                client, query, max_results=max_results, time_range=time_range
            )
        except Exception as exc:  # une source en echec ne doit pas bloquer les autres
            logger.warning("Source %s erreur pour %r: %s", name, query, exc)
            continue
        for r in results:
            url = r.get("url")
            if url:
                merged.setdefault(url, r)
    return list(merged.values())
