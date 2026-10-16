"""Sécurité : hachage des mots de passe (bcrypt) et JWT (HS256)."""
from __future__ import annotations

import datetime as dt
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import get_settings

settings = get_settings()

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_access_token(subject: int | str, ttl_min: int | None = None) -> str:
    expire = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        minutes=ttl_min or settings.access_token_ttl_min
    )
    payload: dict[str, Any] = {"sub": str(subject), "exp": expire}
    return jwt.encode(
        payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> int | None:
    """Retourne l'id utilisateur encodé, ou None si jeton invalide/expiré."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        return None
    sub = payload.get("sub")
    return int(sub) if sub is not None and str(sub).isdigit() else None
