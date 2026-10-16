"""Recherche unifiée : SearXNG d'abord, repli Serper si SearXNG ne renvoie rien.

SearXNG est gratuit mais rate-limité (moteurs suspendus -> liste vide). Serper
(API Google à clé) sert de secours : on ne l'appelle QUE si SearXNG revient
vide, pour économiser son quota.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from . import searxng, serper

logger = logging.getLogger(__name__)


async def search(
    client: httpx.AsyncClient,
    query: str,
    *,
    max_results: int = 15,
    time_range: Optional[str] = None,
) -> list[dict[str, Any]]:
    results = await searxng.search(
        client, query, max_results=max_results, time_range=time_range
    )
    if results:
        return results
    if serper.enabled():
        logger.info("SearXNG vide pour %r -> repli Serper", query)
        results = await serper.search(
            client, query, max_results=max_results, time_range=time_range
        )
    return results
