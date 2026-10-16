"""Thèmes : CRUD + déclenchement de scan. Propriété de l'utilisateur courant."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Theme, User
from ..scheduler import trigger_scan
from ..schemas import ScanResult, ThemeCreate, ThemeOut, ThemeUpdate

router = APIRouter(prefix="/themes", tags=["themes"])


def _owned_theme(db: Session, theme_id: int, user: User) -> Theme:
    theme = db.get(Theme, theme_id)
    if theme is None or theme.user_id != user.id:
        raise HTTPException(status_code=404, detail="Thème introuvable")
    return theme


@router.get("", response_model=list[ThemeOut])
def list_themes(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Theme]:
    return list(
        db.scalars(
            select(Theme).where(Theme.user_id == user.id).order_by(Theme.created_at.desc())
        )
    )


@router.post("", response_model=ThemeOut, status_code=status.HTTP_201_CREATED)
def create_theme(
    payload: ThemeCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Theme:
    theme = Theme(
        user_id=user.id,
        name=payload.name,
        description=payload.description,
        scan_interval_hours=payload.scan_interval_hours,
        lookback_hours=payload.lookback_hours,
    )
    db.add(theme)
    db.commit()
    db.refresh(theme)
    trigger_scan(theme.id)  # extrapolation + premier scan en arrière-plan
    return theme


@router.get("/{theme_id}", response_model=ThemeOut)
def get_theme(
    theme_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Theme:
    return _owned_theme(db, theme_id, user)


@router.patch("/{theme_id}", response_model=ThemeOut)
def update_theme(
    theme_id: int,
    payload: ThemeUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Theme:
    theme = _owned_theme(db, theme_id, user)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(theme, key, value)
    db.commit()
    db.refresh(theme)
    return theme


@router.delete("/{theme_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_theme(
    theme_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    theme = _owned_theme(db, theme_id, user)
    db.delete(theme)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{theme_id}/scan", response_model=ScanResult)
def scan(
    theme_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScanResult:
    _owned_theme(db, theme_id, user)
    trigger_scan(theme_id)
    # Scan asynchrone en arrière-plan : on répond immédiatement.
    return ScanResult(theme_id=theme_id, queries=0, new_articles=0, clusters=0)
