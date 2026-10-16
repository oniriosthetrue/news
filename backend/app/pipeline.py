"""Pipeline de scan d'un thème.

Flux : thème -> (LLM) requêtes élargies -> (SearXNG) résultats -> scraping ->
dédup par URL -> regroupement par similarité de titre -> (LLM) titre+résumé de
chaque cluster -> persistance.

Conception :
- Les requêtes extrapolées sont MISES EN CACHE en base (table `queries`) et
  réutilisées tant qu'elles existent -> un seul appel LLM d'extrapolation par
  thème (à la création), pas à chaque scan.
- Seuls les articles NOUVEAUX (URL jamais vue) sont scrapés et clusterisés.
- La concurrence LLM/scraping est bornée pour ne pas saturer vLLM partagé.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import logging
import re
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Article, Cluster, Query, Theme
from .clients import llm, searxng, scrape

logger = logging.getLogger(__name__)
settings = get_settings()

_TOKEN_RE = re.compile(r"[a-zà-ÿ0-9]+")


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()


def _domain(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


async def _ensure_queries(
    client: httpx.AsyncClient, db: Session, theme: Theme
) -> list[str]:
    """Retourne les requêtes du thème ; les extrapole via LLM si absentes."""
    existing = db.scalars(select(Query.text).where(Query.theme_id == theme.id)).all()
    if existing:
        return list(existing)
    queries = await llm.extrapolate_queries(
        client, theme.name, theme.description, settings.max_queries_per_theme
    )
    for q in queries:
        db.add(Query(theme_id=theme.id, text=q))
    db.commit()
    logger.info("Thème %s : %d requêtes extrapolées", theme.id, len(queries))
    return queries


async def _gather_candidates(
    client: httpx.AsyncClient, queries: list[str]
) -> list[dict]:
    """Interroge SearXNG pour chaque requête (concurrence bornée)."""
    sem = asyncio.Semaphore(settings.llm_concurrency)

    async def one(query: str) -> list[dict]:
        async with sem:
            return await searxng.search(
                client, query, max_results=settings.max_results_per_query
            )

    chunks = await asyncio.gather(*(one(q) for q in queries))
    merged: dict[str, dict] = {}
    for chunk in chunks:
        for r in chunk:
            merged.setdefault(r["url"], r)
    return list(merged.values())


def _existing_hashes(db: Session, urls: list[str]) -> set[str]:
    hashes = {_url_hash(u) for u in urls}
    if not hashes:
        return set()
    rows = db.scalars(select(Article.url_hash).where(Article.url_hash.in_(hashes)))
    return set(rows)


async def _scrape_new(
    client: httpx.AsyncClient, candidates: list[dict]
) -> list[dict]:
    """Scrape les candidats (concurrence bornée) ; garde ceux avec contenu."""
    sem = asyncio.Semaphore(settings.llm_concurrency + 2)

    async def one(cand: dict) -> dict | None:
        async with sem:
            art = await scrape.scrape(client, cand["url"])
        if art is None:
            return None
        return {**cand, "_scraped": art}

    results = await asyncio.gather(*(one(c) for c in candidates))
    return [r for r in results if r]


def _group_by_similarity(items: list[dict], threshold: float = 0.35) -> list[list[dict]]:
    """Regroupe les articles par recoupement de titres (Jaccard). Simple et borné."""
    groups: list[list[dict]] = []
    group_tokens: list[set[str]] = []
    for it in items:
        toks = _tokens(it.get("title", "") or it["url"])
        best, best_score = -1, 0.0
        for i, gt in enumerate(group_tokens):
            score = _jaccard(toks, gt)
            if score > best_score:
                best, best_score = i, score
        if best >= 0 and best_score >= threshold:
            groups[best].append(it)
            group_tokens[best] |= toks
        else:
            groups.append([it])
            group_tokens.append(toks)
    return groups


async def _persist_cluster(
    client: httpx.AsyncClient, db: Session, theme: Theme, group: list[dict]
) -> Cluster:
    title, summary = await llm.summarize_cluster(
        client,
        theme.name,
        [
            {
                "source": _domain(g["url"]),
                "title": g.get("title", ""),
                "snippet": g.get("snippet", ""),
                "content": getattr(g["_scraped"], "content", ""),
            }
            for g in group
        ],
    )
    cluster = Cluster(
        theme_id=theme.id,
        title=title or (group[0].get("title") or theme.name)[:500],
        summary=summary,
        score=float(len(group)),
    )
    db.add(cluster)
    db.flush()  # obtient cluster.id

    for g in group:
        scraped = g["_scraped"]
        published = None
        if scraped.published_at:
            try:
                published = dt.datetime.fromisoformat(
                    scraped.published_at.replace("Z", "+00:00")
                )
            except ValueError:
                published = None
        db.add(
            Article(
                url=g["url"],
                url_hash=_url_hash(g["url"]),
                title=(scraped.title or g.get("title", ""))[:500],
                source=_domain(g["url"]),
                content=scraped.content,
                image_url=scraped.image_url,
                published_at=published,
                cluster_id=cluster.id,
            )
        )
    return cluster


async def scan_theme(db: Session, theme_id: int) -> dict:
    """Exécute un scan complet d'un thème. Retourne un compte-rendu."""
    theme = db.get(Theme, theme_id)
    if theme is None:
        raise ValueError(f"Thème {theme_id} introuvable")

    async with httpx.AsyncClient() as client:
        queries = await _ensure_queries(client, db, theme)
        candidates = await _gather_candidates(client, queries)

        known = _existing_hashes(db, [c["url"] for c in candidates])
        fresh = [c for c in candidates if _url_hash(c["url"]) not in known]
        fresh = fresh[: settings.max_articles_per_scan]

        scraped = await _scrape_new(client, fresh)

        groups = _group_by_similarity(scraped)
        # Limite le nombre de clusters (donc d'appels LLM de résumé) par scan.
        groups = sorted(groups, key=len, reverse=True)[: settings.max_queries_per_theme]

        clusters = 0
        for group in groups:
            if not group:
                continue
            await _persist_cluster(client, db, theme, group)
            clusters += 1

        theme.last_scanned_at = dt.datetime.now(dt.timezone.utc)
        db.commit()

        new_articles = sum(len(g) for g in groups)
        logger.info(
            "Scan thème %s : %d req, %d nouveaux articles, %d clusters",
            theme_id, len(queries), new_articles, clusters,
        )
        return {
            "theme_id": theme_id,
            "queries": len(queries),
            "new_articles": new_articles,
            "clusters": clusters,
        }
