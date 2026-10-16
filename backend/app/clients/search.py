"""Recherche unifiée : SearXNG d'abord, puis replis sur API à clé si vide.

SearXNG est gratuit mais rate-limité (moteurs suspendus -> liste vide). Quand
il ne renvoie rien, on essaie des API de news par clé, dans l'ordre :
NewsAPI -> GNews -> Serper. Chaque repli n'est appelé QUE si le précédent
revient vide ET si sa clé est configurée, pour économiser les quotas.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from ..config import get_settings
from . import gnews, newsapi, searxng, serper

logger = logging.getLogger(__name__)
settings = get_settings()

# Replis ordonnés : (nom, module). Appelés si SearXNG désactivé ou revient vide.
_FALLBACKS = (("NewsAPI", newsapi), ("GNews", gnews), ("Serper", serper))


async def search(
    client: httpx.AsyncClient,
    query: str,
    *,
    max_results: int = 15,
    time_range: Optional[str] = None,
) -> list[dict[str, Any]]:
    # SearXNG d'abord, sauf si désactivé (instance partagée -> quota saturé).
    if settings.searxng_enabled:
        results = await searxng.search(
            client, query, max_results=max_results, time_range=time_range
        )
        if results:
            return results

    for name, mod in _FALLBACKS:
        if not mod.enabled():
            continue
        logger.info("SearXNG indisponible pour %r -> repli %s", query, name)
        results = await mod.search(
            client, query, max_results=max_results, time_range=time_range
        )
        if results:
            return results
    return results
