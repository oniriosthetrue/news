"""Ordonnanceur : scan périodique des thèmes actifs.

APScheduler (BackgroundScheduler) exécute les scans dans des threads dédiés,
chacun avec sa propre session SQLAlchemy et sa propre boucle asyncio (le
pipeline est asynchrone). Un verrou par thème évite les scans qui se chevauchent.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .models import Theme
from .pipeline import scan_theme

logger = logging.getLogger(__name__)
settings = get_settings()

_scheduler: BackgroundScheduler | None = None
_scan_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(theme_id: int) -> threading.Lock:
    with _locks_guard:
        return _scan_locks.setdefault(theme_id, threading.Lock())


def _run_scan(theme_id: int) -> None:
    """Corps du job : thread dédié + session + boucle asyncio propres."""
    lock = _lock_for(theme_id)
    if not lock.acquire(blocking=False):
        logger.info("Scan thème %s déjà en cours, ignoré", theme_id)
        return
    try:
        with SessionLocal() as db:
            asyncio.run(scan_theme(db, theme_id))
    except Exception:  # noqa: BLE001 — un job ne doit jamais tuer l'ordonnanceur
        logger.exception("Échec du scan du thème %s", theme_id)
    finally:
        lock.release()


def trigger_scan(theme_id: int) -> None:
    """Déclenche un scan immédiat (utilisé par l'API POST /themes/{id}/scan)."""
    if _scheduler is None:
        # Fallback hors contexte ordonnanceur (tests) : thread unique.
        threading.Thread(target=_run_scan, args=(theme_id,), daemon=True).start()
        return
    _scheduler.add_job(
        _run_scan, args=[theme_id], id=f"scan-{theme_id}", replace_existing=True
    )


def _due_themes() -> list[int]:
    """Thèmes actifs dont la dernière scan est plus vieux que leur intervalle."""
    with SessionLocal() as db:
        themes = db.scalars(
            select(Theme).where(Theme.is_active.is_(True))
        ).all()
        now = dt.datetime.now(dt.timezone.utc)
        due: list[int] = []
        for t in themes:
            if t.last_scanned_at is None:
                due.append(t.id)
                continue
            last = t.last_scanned_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=dt.timezone.utc)
            if now - last >= dt.timedelta(hours=t.scan_interval_hours):
                due.append(t.id)
        return due


def _tick() -> None:
    """Tick régulier : met en file un scan pour chaque thème à jour."""
    try:
        for theme_id in _due_themes():
            if _scheduler is not None:
                _scheduler.add_job(
                    _run_scan,
                    args=[theme_id],
                    id=f"scan-{theme_id}",
                    replace_existing=True,
                )
    except Exception:  # noqa: BLE001
        logger.exception("Erreur dans le tick de l'ordonnanceur")


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    # Tick toutes les 10 min : vérifie les thèmes échus et programme leurs scans.
    _scheduler.add_job(_tick, "interval", minutes=10, id="tick", max_instances=1)
    _scheduler.start()
    logger.info("Ordonnanceur démarré (tick 10 min, intervalle défaut %dh)",
                settings.scan_default_interval_hours)
    # Premier passage rapide au démarrage.
    _scheduler.add_job(_tick, id="tick-boot")
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
