"""Point d'entrée FastAPI — `news.minervia.fr` backend."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  — enregistre les tables sur Base.metadata
from .config import get_settings
from .db import Base, engine
from .routers import auth, news, themes, usage
from .scheduler import shutdown_scheduler, start_scheduler

settings = get_settings()
logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)


def _migrate_add_columns() -> None:
    """Ajoute les colonnes manquantes sur les tables existantes (pas d'Alembic).

    `create_all` ne modifie pas une table déjà créée : on ajoute à la main les
    colonnes introduites après le déploiement initial, de façon idempotente.
    """
    from sqlalchemy import text

    adds = [
        "ALTER TABLE themes ADD COLUMN IF NOT EXISTS lookback_hours integer NOT NULL DEFAULT 24",
    ]
    with engine.begin() as conn:
        for stmt in adds:
            conn.execute(text(stmt))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Création des tables au démarrage (schéma simple, pas de migration).
    Base.metadata.create_all(bind=engine)
    _migrate_add_columns()
    logger.info("Schéma base vérifié/créé")
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(
    title="news.minervia.fr API",
    version="1.0.0",
    lifespan=lifespan,
    root_path="",
)

# Origine même (Traefik sert web + api sous le même hôte) ; CORS large en dév.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(themes.router, prefix="/api")
app.include_router(news.router, prefix="/api")
app.include_router(usage.router, prefix="/api")


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.litellm_model}
