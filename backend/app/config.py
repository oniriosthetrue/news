"""Configuration via variables d'environnement (pydantic-settings)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Base de données ---
    database_url: str = "postgresql+psycopg://news:news@db:5432/news"

    # --- Auth ---
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 1440

    # --- LiteLLM (passerelle LLM existante) ---
    litellm_base_url: str = "http://litellm:4000/v1"
    litellm_api_key: str = ""
    litellm_model: str = "IA"

    # --- SearXNG (méta-moteur existant) ---
    searxng_url: str = "http://searxng:8080/search"
    searxng_language: str = "fr-FR"
    searxng_time_range: str = "day"

    # --- Pipeline ---
    scan_default_interval_hours: int = 6
    max_queries_per_theme: int = 8
    max_results_per_query: int = 15
    max_articles_per_scan: int = 120
    llm_concurrency: int = 2
    http_timeout: float = 30.0
    scrape_timeout: float = 20.0

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
