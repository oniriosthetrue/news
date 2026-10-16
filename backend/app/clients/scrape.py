"""Scraping : extraction du contenu lisible d'une page article (trafilatura)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import httpx
import trafilatura

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Motifs d'URL qui designent un portail / formulaire / appli, pas un article.
_NON_ARTICLE_URL = (
    "/search", "searchby", "publicsearch", "/ui/", "/query", "/lookup",
    "/login", "/signin", "/signup", "/register", "/account", "/cart",
    "/checkout", "/subscribe", "/newsletter", "/contact", "/about",
    "/privacy", "/legal", "/terms", "/sitemap", "/tag/", "/category/",
    "/author/", "?page=", "wp-login", "wp-admin",
)

# Mots de formulaire/navigation : si le contenu en est sature, ce n'est pas un article.
_BOILERPLATE_WORDS = (
    "search", "submit", "filter", "advanced search", "query", "clear",
    "rechercher", "envoyer", "filtre", "connexion", "mot de passe",
    "sign in", "log in", "copyright", "all rights reserved", "cookie",
    "javascript", "enable javascript", "browser",
)


def _looks_like_article(content: str) -> bool:
    """Faux si le texte est un formulaire/portail plutot qu'un article."""
    text = content.lower()
    hits = sum(1 for w in _BOILERPLATE_WORDS if w in text)
    # Beaucoup de mots de formulaire pour peu de texte -> page utilitaire.
    if hits >= 3 and len(content) < 1500:
        return False
    return True


@dataclass
class ScrapedArticle:
    title: str
    content: str
    image_url: Optional[str]
    published_at: Optional[str]


def _is_article_url(url: str) -> bool:
    lowered = url.lower()
    return not any(token in lowered for token in _NON_ARTICLE_URL)


def _extract(html: str, url: str) -> Optional[ScrapedArticle]:
    meta = trafilatura.extract_metadata(html, default_url=url)
    content = trafilatura.extract(
        html, url=url, include_comments=False, favor_recall=True
    )
    if not content or len(content) < 120:
        return None
    if not _looks_like_article(content):
        return None
    return ScrapedArticle(
        title=(meta.title if meta else "") or "",
        content=content,
        image_url=(meta.image if meta else None),
        published_at=(meta.date if meta else None),
    )


async def scrape(client: httpx.AsyncClient, url: str) -> Optional[ScrapedArticle]:
    """Récupère et extrait le contenu lisible. Retourne None si échec/contenu trop court."""
    if not _is_article_url(url):
        logger.debug("URL non-article ignorée: %s", url)
        return None
    try:
        resp = await client.get(
            url,
            headers={"User-Agent": _UA},
            timeout=settings.scrape_timeout,
            follow_redirects=True,
        )
        if resp.status_code != 200 or "html" not in resp.headers.get(
            "content-type", ""
        ):
            return None
        html = resp.text
    except httpx.HTTPError as exc:
        logger.debug("Scrape échoué %s: %s", url, exc)
        return None

    # trafilatura est synchrone/CPU -> on le déporte hors de la boucle événementielle.
    return await asyncio.to_thread(_extract, html, url)
