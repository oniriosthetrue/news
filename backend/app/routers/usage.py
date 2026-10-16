"""Usage des sources de recherche : solde de credits Serper (stock non renouvelable)."""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends

from ..clients import gnews, newsapi, search, serper
from ..config import get_settings
from ..deps import get_current_user
from ..models import User

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("")
async def usage(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Etat des sources de recherche + solde de credits Serper."""
    settings = get_settings()
    order = [name for name, _ in search._SOURCES]
    out: dict[str, Any] = {
        "searxng_enabled": settings.searxng_enabled,
        "fallback_order": order,
        "enabled": {
            "serper": serper.enabled(),
            "newsapi": newsapi.enabled(),
            "gnews": gnews.enabled(),
        },
        "serper": None,
    }
    if serper.enabled():
        async with httpx.AsyncClient() as client:
            out["serper"] = await serper.get_balance(client)
    return out
