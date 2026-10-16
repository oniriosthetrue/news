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


@router.post("/theme-command")
async def theme_command(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Exécute une écriture thème DÉLÉGUÉE par le miroir VPS (flux VPS -> boîtier).

    Le miroir est en lecture seule : créer/scaner/modifier/supprimer un thème sur
    le site public est relayé ici, exécuté par le boîtier (seul à pouvoir scanner),
    puis repoussé vers le miroir. Protégé par la même signature HMAC que l'import.
    Actif uniquement quand la sync est activée (= on est le boîtier/moteur).
    """
    if not settings.sync_enabled:
        raise HTTPException(status_code=404, detail="Réservé au boîtier (moteur)")
    secret = settings.sync_shared_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Secret de sync non configuré")
    body = await request.body()
    if not verify_signature(secret, body, request.headers.get("X-Signature", "")):
        raise HTTPException(status_code=401, detail="Signature invalide")

    import json as _json

    from ..models import Theme
    from ..scheduler import _engine_status, trigger_scan
    from ..sync import build_snapshot, push_snapshot

    async def _push_now() -> None:
        """Pousse l'instantané courant vers le miroir (dans la boucle active).

        Version async de scheduler.push_to_vps (celle-ci appelle asyncio.run,
        impossible dans un endpoint async déjà en cours d'exécution).
        """
        import httpx

        try:
            engine = await _engine_status()
            snapshot = build_snapshot(db, engine_status=engine)
            async with httpx.AsyncClient() as client:
                await push_snapshot(client, snapshot)
        except Exception:  # noqa: BLE001 — le relais ne doit jamais casser la réponse
            import logging

            logging.getLogger(__name__).exception("Push post-commande échoué")

    try:
        cmd = _json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="JSON invalide")

    action = cmd.get("action")
    user_id = cmd.get("user_id")
    theme_id = cmd.get("theme_id")
    data = cmd.get("data") or {}

    def _serialize(t: Theme) -> dict[str, Any]:
        return {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "scan_interval_hours": t.scan_interval_hours,
            "lookback_hours": t.lookback_hours,
            "is_active": t.is_active,
            "last_scanned_at": t.last_scanned_at.isoformat() if t.last_scanned_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }

    if action == "create":
        theme = Theme(
            user_id=user_id,
            name=data.get("name", ""),
            description=data.get("description", ""),
            scan_interval_hours=data.get("scan_interval_hours", 6),
            lookback_hours=data.get("lookback_hours", 24),
        )
        db.add(theme)
        db.commit()
        db.refresh(theme)
        await _push_now()  # le thème apparaît tout de suite au miroir (liste)
        trigger_scan(theme.id)  # extrapolation + 1er scan -> push post-scan (articles)
        return {"status": "ok", "theme": _serialize(theme)}

    theme = db.get(Theme, theme_id) if theme_id else None
    if theme is None or theme.user_id != user_id:
        raise HTTPException(status_code=404, detail="Thème introuvable")

    if action == "update":
        for key, value in data.items():
            if value is not None and hasattr(theme, key):
                setattr(theme, key, value)
        db.commit()
        db.refresh(theme)
        await _push_now()  # le miroir doit refléter la modif
        return {"status": "ok", "theme": _serialize(theme)}

    if action == "delete":
        db.delete(theme)
        db.commit()
        await _push_now()
        return {"status": "ok"}

    if action == "scan":
        trigger_scan(theme.id)
        return {"status": "ok"}

    raise HTTPException(status_code=400, detail="Action inconnue")


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
