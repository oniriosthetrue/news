"""Schémas Pydantic (entrée/sortie API)."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --- Auth / users ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=120)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    display_name: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# --- Themes ---
class ThemeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    scan_interval_hours: int = Field(default=6, ge=1, le=168)
    lookback_hours: int = Field(default=24, ge=1, le=8760)


class ThemeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    scan_interval_hours: Optional[int] = Field(default=None, ge=1, le=168)
    lookback_hours: Optional[int] = Field(default=None, ge=1, le=8760)
    is_active: Optional[bool] = None


class ThemeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str
    scan_interval_hours: int
    lookback_hours: int
    is_active: bool
    last_scanned_at: Optional[dt.datetime]
    created_at: dt.datetime


# --- News feed ---
class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    url: str
    title: str
    source: str
    image_url: Optional[str]
    published_at: Optional[dt.datetime]


class ClusterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    theme_id: int
    title: str
    summary: str
    score: float
    created_at: dt.datetime
    updated_at: dt.datetime
    articles: list[ArticleOut]


class ScanResult(BaseModel):
    theme_id: int
    queries: int
    new_articles: int
    clusters: int
