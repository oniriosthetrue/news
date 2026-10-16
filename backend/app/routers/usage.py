"""Usage des sources de recherche : solde de credits Serper (stock non renouvelable)."""
from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..clients import gnews, llm, newsapi, search, serper
from ..config import get_settings
from ..db import get_db
from ..deps import get_current_user
from ..models import EngineStatus, User

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("")
async def usage(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Etat des sources de recherche + solde de credits Serper.

    - Boîtier : sonde son propre LiteLLM + solde Serper en direct.
    - Miroir VPS : n'a pas de LiteLLM -> affiche l'état du moteur POUSSÉ par le
      boîtier dans le dernier instantané (table engine_status).
    """
    settings = get_settings()
    order = [name for name, _ in search._SOURCES]

    if settings.mirror_mode:
        status = db.get(EngineStatus, 1)
        enabled = json.loads(status.enabled_sources) if status else {}
        return {
            "searxng_enabled": settings.searxng_enabled,
            "fallback_order": order,
            "enabled": enabled,
            "serper": (
                {"balance": status.serper_balance}
                if status and status.serper_balance is not None
                else None
            ),
            "mirror_mode": True,
            "llm_online": bool(status.llm_online) if status else False,
            "snapshot_at": status.snapshot_at.isoformat() if status and status.snapshot_at else None,
        }

    out: dict[str, Any] = {
        "searxng_enabled": settings.searxng_enabled,
        "fallback_order": order,
        "enabled": {
            "serper": serper.enabled(),
            "newsapi": newsapi.enabled(),
            "gnews": gnews.enabled(),
        },
        "serper": None,
        # Indicateur « LLM on/off » : la passerelle LiteLLM est-elle joignable ?
        "mirror_mode": settings.mirror_mode,
        "llm_online": False,
    }
    async with httpx.AsyncClient() as client:
        out["llm_online"] = await llm.online(client)
        if serper.enabled():
            out["serper"] = await serper.get_balance(client)
    return out
