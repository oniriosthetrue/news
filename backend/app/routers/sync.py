"""Endpoint d'import pour le VPS miroir : reçoit l'instantané poussé par le boîtier.

Sécurité : signature HMAC-SHA256 du corps brut, vérifiée avec le secret partagé
(`SYNC_SHARED_SECRET`). Aucune auth utilisateur : seul le porteur du secret peut
pousser. Actif uniquement en mode miroir.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..sync import import_snapshot, verify_signature

router = APIRouter(prefix="/sync", tags=["sync"])
settings = get_settings()


@router.get("/engine-status")
async def engine_status(request: Request) -> dict[str, Any]:
    """État moteur du BOÎTIER, sondé en direct par le miroir VPS (flux VPS -> boîtier).

    Protégé par la même signature HMAC que l'import (corps vide pour un GET).
    Actif uniquement quand la sync est activée (= on est le boîtier/moteur).
    Le miroir s'en sert pour son badge « LLM on/off » en temps réel.
    """
    if not settings.sync_enabled:
        raise HTTPException(status_code=404, detail="Réservé au boîtier (moteur)")
    secret = settings.sync_shared_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Secret de sync non configuré")
    signature = request.headers.get("X-Signature", "")
    if not verify_signature(secret, b"", signature):
        raise HTTPException(status_code=401, detail="Signature invalide")

    import httpx

    from ..clients import gnews, llm, newsapi, serper

    async with httpx.AsyncClient() as client:
        llm_online = await llm.online(client)
        balance = await serper.get_balance(client) if serper.enabled() else None
    return {
        "llm_online": llm_online,
        "serper_balance": (balance or {}).get("balance"),
        "enabled": {
            "serper": serper.enabled(),
            "newsapi": newsapi.enabled(),
            "gnews": gnews.enabled(),
        },
    }


@router.post("/import")
async def sync_import(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not settings.mirror_mode:
        raise HTTPException(status_code=404, detail="Mode miroir désactivé")

    secret = settings.sync_shared_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Secret de sync non configuré")

    body = await request.body()
    signature = request.headers.get("X-Signature", "")
    if not verify_signature(secret, body, signature):
        raise HTTPException(status_code=401, detail="Signature invalide")

    import json

    try:
        snapshot = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="JSON invalide")

    counts = import_snapshot(db, snapshot)
    return {"status": "ok", **counts}
