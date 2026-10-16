"""Synchronisation boîtier -> VPS (miroir en lecture seule).

Le boîtier (moteur : recherche web + LLM) construit un INSTANTANÉ complet des
données visibles (users, thèmes, clusters, articles) et le Pousse vers le VPS
via une API signée (HMAC-SHA256). Le VPS, en mode miroir, remplace son contenu
par cet instantané. Le VPS n'a jamais besoin du LLM : il ne fait que recevoir
et afficher.

- Boîtier éteint  -> le VPS sert le dernier instantané reçu.
- Boîtier rallumé -> les scans reprennent et repoussent un nouvel instantané.

Signature : l'en-tête `X-Signature` contient HMAC_SHA256(secret, corps_brut).
Le même secret est configuré des deux côtés (`SYNC_SHARED_SECRET`).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
from typing import Any, Optional

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Article, Cluster, EngineStatus, Theme, User

logger = logging.getLogger(__name__)
settings = get_settings()


def _iso(value: Optional[dt.datetime]) -> Optional[str]:
    return value.isoformat() if value else None


# --------------------------------------------------------------------------- #
# Construction de l'instantané (côté boîtier)
# --------------------------------------------------------------------------- #
def build_snapshot(
    db: Session, engine_status: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Sérialise toutes les données visibles en un dict JSON-compatible.

    On INCLUT `content` (corps texte scrapé) : le miroir réplique le texte de
    chaque article et l'affiche avec un lien vers la source d'origine. On garde
    aussi titre, résumé, source, URL, image, dates.

    `engine_status` (optionnel) : état du moteur calculé par le boîtier
    ({"llm_online": bool, "serper_balance": int|None, "enabled": {...}}). Le
    miroir ne peut pas sonder son propre LLM (il n'en a pas) : il affiche celui-ci.
    """
    users = db.scalars(select(User)).all()
    themes = db.scalars(select(Theme)).all()
    clusters = db.scalars(select(Cluster)).all()

    snap: dict[str, Any] = {
        "generated_at": _iso(dt.datetime.now(dt.timezone.utc)),
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "password_hash": u.password_hash,
                "display_name": u.display_name,
                "is_active": u.is_active,
                "created_at": _iso(u.created_at),
            }
            for u in users
        ],
        "themes": [
            {
                "id": t.id,
                "user_id": t.user_id,
                "name": t.name,
                "description": t.description,
                "scan_interval_hours": t.scan_interval_hours,
                "lookback_hours": t.lookback_hours,
                "is_active": t.is_active,
                "last_scanned_at": _iso(t.last_scanned_at),
                "created_at": _iso(t.created_at),
            }
            for t in themes
        ],
        "clusters": [
            {
                "id": c.id,
                "theme_id": c.theme_id,
                "title": c.title,
                "summary": c.summary,
                "score": c.score,
                "created_at": _iso(c.created_at),
                "updated_at": _iso(c.updated_at),
                "articles": [
                    {
                        "id": a.id,
                        "url": a.url,
                        "url_hash": a.url_hash,
                        "title": a.title,
                        "source": a.source,
                        "content": a.content,
                        "image_url": a.image_url,
                        "published_at": _iso(a.published_at),
                        "fetched_at": _iso(a.fetched_at),
                    }
                    for a in c.articles
                ],
            }
            for c in clusters
        ],
    }
    if engine_status is not None:
        snap["engine_status"] = engine_status
    return snap


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    if not secret:
        return False
    expected = sign(secret, body)
    return hmac.compare_digest(expected, signature or "")


# --------------------------------------------------------------------------- #
# Push (côté boîtier)
# --------------------------------------------------------------------------- #
async def push_snapshot(client: httpx.AsyncClient, snapshot: dict[str, Any]) -> bool:
    """Envoie l'instantané vers le VPS. True si accepté."""
    if not settings.sync_target_url or not settings.sync_shared_secret:
        logger.warning("Sync non configurée (target/secret) — push ignoré")
        return False
    url = settings.sync_target_url.rstrip("/") + "/api/sync/import"
    body = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
    signature = sign(settings.sync_shared_secret, body)
    try:
        resp = await client.post(
            url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature,
            },
            timeout=settings.sync_timeout,
        )
    except httpx.HTTPError as exc:
        logger.warning("Push sync vers %s échoué: %s", url, exc)
        return False
    if resp.status_code >= 400:
        logger.warning("Push sync %s -> %s: %s", url, resp.status_code, resp.text[:200])
        return False
    logger.info("Push sync OK (%s) -> %s", resp.status_code, resp.text[:120])
    return True


# --------------------------------------------------------------------------- #
# Probe temps réel (côté VPS miroir) — VPS -> boîtier, pour le badge LLM
# --------------------------------------------------------------------------- #
async def probe_engine_status(client: httpx.AsyncClient) -> Optional[dict[str, Any]]:
    """Sonde le boîtier en direct pour son état moteur (LLM on/off, credits).

    Flux inverse du push (VPS -> boîtier). Signé HMAC comme l'import, pour que
    seul le miroir puisse appeler l'endpoint. Renvoie le dict d'état, ou None si
    le boîtier est injoignable / mal configuré (le miroir retombe alors sur le
    dernier état poussé).
    """
    if not settings.engine_probe_url or not settings.sync_shared_secret:
        return None
    # Signature sur la chaîne vide : l'endpoint est un GET sans corps.
    signature = sign(settings.sync_shared_secret, b"")
    headers = {"X-Signature": signature}
    if settings.engine_probe_host:
        headers["Host"] = settings.engine_probe_host
    try:
        resp = await client.get(
            settings.engine_probe_url,
            headers=headers,
            timeout=settings.engine_probe_timeout,
        )
    except httpx.HTTPError as exc:
        logger.info("Probe boîtier injoignable (%s)", exc)
        return None
    if resp.status_code >= 400:
        logger.info("Probe boîtier -> %s: %s", resp.status_code, resp.text[:160])
        return None
    try:
        return resp.json()
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Relais des écritures thème (côté VPS miroir) — VPS -> boîtier
# --------------------------------------------------------------------------- #
async def send_theme_command(
    client: httpx.AsyncClient, command: dict[str, Any]
) -> dict[str, Any]:
    """Relaye une écriture thème vers le boîtier, qui l'exécute et repousse.

    Utilisé par le miroir (lecture seule) : créer/scaner/modifier/supprimer un
    thème sur le site public est délégué au boîtier (seul à pouvoir scanner).
    Lève HTTPException(502) si le boîtier est injoignable ou refuse.
    """
    from fastapi import HTTPException

    if not settings.engine_command_url or not settings.sync_shared_secret:
        raise HTTPException(
            status_code=503,
            detail="Miroir non configuré pour déléguer au boîtier",
        )
    body = json.dumps(command, ensure_ascii=False).encode("utf-8")
    signature = sign(settings.sync_shared_secret, body)
    headers = {
        "Content-Type": "application/json",
        "X-Signature": signature,
    }
    if settings.engine_probe_host:
        headers["Host"] = settings.engine_probe_host
    try:
        resp = await client.post(
            settings.engine_command_url,
            content=body,
            headers=headers,
            timeout=settings.sync_timeout,
        )
    except httpx.HTTPError as exc:
        logger.warning("Relais thème -> boîtier injoignable: %s", exc)
        raise HTTPException(
            status_code=502, detail="Boîtier injoignable (création impossible)"
        )
    if resp.status_code >= 400:
        logger.warning(
            "Relais thème -> boîtier %s: %s", resp.status_code, resp.text[:200]
        )
        raise HTTPException(
            status_code=502, detail=f"Refus du boîtier : {resp.text[:200]}"
        )
    try:
        return resp.json()
    except ValueError:
        return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Import (côté VPS miroir) — remplace tout le contenu par l'instantané
# --------------------------------------------------------------------------- #
def _parse_dt(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def import_snapshot(db: Session, snapshot: dict[str, Any]) -> dict[str, int]:
    """Remplace le contenu du miroir par l'instantané reçu (transaction unique).

    On réinsère avec les MÊMES ids que le boîtier, puis on resynchronise les
    séquences. Le miroir étant en lecture seule, aucun id futur n'est créé ici.
    """
    users = snapshot.get("users", [])
    themes = snapshot.get("themes", [])
    clusters = snapshot.get("clusters", [])
    engine = snapshot.get("engine_status")

    # Purge dans l'ordre (les FK en cascade prennent le relais, mais on est explicite).
    db.execute(text("DELETE FROM articles"))
    db.execute(text("DELETE FROM clusters"))
    db.execute(text("DELETE FROM queries"))
    db.execute(text("DELETE FROM themes"))
    db.execute(text("DELETE FROM users"))

    for u in users:
        db.add(
            User(
                id=u["id"],
                email=u["email"],
                password_hash=u["password_hash"],
                display_name=u.get("display_name", ""),
                is_active=u.get("is_active", True),
            )
        )
    for t in themes:
        db.add(
            Theme(
                id=t["id"],
                user_id=t["user_id"],
                name=t["name"],
                description=t.get("description", ""),
                scan_interval_hours=t.get("scan_interval_hours", 6),
                lookback_hours=t.get("lookback_hours", 24),
                is_active=t.get("is_active", True),
                last_scanned_at=_parse_dt(t.get("last_scanned_at")),
            )
        )
    n_articles = 0
    for c in clusters:
        cluster = Cluster(
            id=c["id"],
            theme_id=c["theme_id"],
            title=c["title"],
            summary=c.get("summary", ""),
            score=c.get("score", 0.0),
        )
        for a in c.get("articles", []):
            cluster.articles.append(
                Article(
                    id=a["id"],
                    url=a["url"],
                    url_hash=a["url_hash"],
                    title=a.get("title", ""),
                    source=a.get("source", ""),
                    content=a.get("content", ""),
                    image_url=a.get("image_url"),
                    published_at=_parse_dt(a.get("published_at")),
                )
            )
            n_articles += 1
        db.add(cluster)

    # Etat du moteur poussé par le boîtier (ligne unique id=1) -> /api/usage miroir.
    if engine is not None:
        import json as _json

        status = db.get(EngineStatus, 1) or EngineStatus(id=1)
        status.llm_online = bool(engine.get("llm_online", False))
        bal = engine.get("serper_balance")
        status.serper_balance = int(bal) if isinstance(bal, (int, float)) else None
        status.enabled_sources = _json.dumps(engine.get("enabled", {}))
        status.snapshot_at = _parse_dt(snapshot.get("generated_at"))
        db.merge(status)

    db.commit()

    # Resynchronise les séquences sur les ids max (propreté, miroir read-only).
    for table, col in (
        ("users", "id"),
        ("themes", "id"),
        ("clusters", "id"),
        ("articles", "id"),
    ):
        db.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{col}'), "
                f"COALESCE((SELECT MAX({col}) FROM {table}), 1))"
            )
        )
    db.commit()

    counts = {
        "users": len(users),
        "themes": len(themes),
        "clusters": len(clusters),
        "articles": n_articles,
    }
    logger.info("Import miroir: %s", counts)
    return counts
