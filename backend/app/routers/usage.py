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
from .. import sync as sync_module

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("")
async def usage(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Etat des sources de recherche + solde de credits Serper.

    - Boîtier : sonde son propre LiteLLM + solde Serper en direct.
    - Miroir VPS : n'a pas de LiteLLM -> SONDE le boîtier en direct (flux VPS ->
      boîtier). Si le boîtier est injoignable, retombe sur le dernier état POUSSÉ
      (table engine_status).
    """
    settings = get_settings()
    order = [name for name, _ in search._SOURCES]

    if settings.mirror_mode:
        # 1) Probe temps réel du boîtier (LLM du boîtier, pas celui du miroir).
        async with httpx.AsyncClient() as client:
            live = await sync_module.probe_engine_status(client)
        if live is not None:
            bal = live.get("serper_balance")
            return {
                "searxng_enabled": settings.searxng_enabled,
                "fallback_order": order,
                "enabled": live.get("enabled", {}),
                "serper": {"balance": bal} if bal is not None else None,
                "mirror_mode": True,
                "llm_online": bool(live.get("llm_online", False)),
                "live": True,
            }
        # 2) Repli : dernier état poussé par le boîtier (boîtier hors ligne).
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
            "live": False,
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
