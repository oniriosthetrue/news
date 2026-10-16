"""Fil d'actualité : clusters regroupés, filtrés par thème de l'utilisateur."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Article, Cluster, Theme, User
from ..schemas import ClusterOut

router = APIRouter(prefix="/news", tags=["news"])


@router.get("", response_model=list[ClusterOut])
def feed(
    theme_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Cluster]:
    stmt = (
        select(Cluster)
        .join(Theme, Cluster.theme_id == Theme.id)
        .where(Theme.user_id == user.id)
    )
    if theme_id is not None:
        owned = db.get(Theme, theme_id)
        if owned is None or owned.user_id != user.id:
            raise HTTPException(status_code=404, detail="Thème introuvable")
        stmt = stmt.where(Cluster.theme_id == theme_id)
    # Tri : actualite la plus recente en haut. On trie par la date de publication
    # la plus recente des articles du cluster (repli : date de creation du
    # cluster). Les clusters plus anciens restent au fil (aucune suppression).
    newest_article = (
        select(func.max(Article.published_at))
        .where(Article.cluster_id == Cluster.id)
        .correlate(Cluster)
        .scalar_subquery()
    )
    stmt = stmt.order_by(
        newest_article.desc().nullslast(), Cluster.created_at.desc()
    ).limit(limit)
    return list(db.scalars(stmt))


@router.get("/clusters/{cluster_id}", response_model=ClusterOut)
def get_cluster(
    cluster_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Cluster:
    cluster = db.get(Cluster, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster introuvable")
    theme = db.get(Theme, cluster.theme_id)
    if theme is None or theme.user_id != user.id:
        raise HTTPException(status_code=404, detail="Cluster introuvable")
    return cluster
