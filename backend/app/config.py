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
    # Désactivable : l'instance est partagée avec OpenWebUI (même IP -> quota
    # commun -> suspensions). false -> la news passe directement aux API à clé.
    searxng_enabled: bool = True
    searxng_url: str = "http://searxng:8080/search"
    searxng_language: str = "fr-FR"
    searxng_time_range: str = "day"

    # --- Replis de recherche (quand SearXNG est rate-limité / vide) ---
    # Ordre d'appel : SearXNG -> NewsAPI -> GNews -> Serper. Chaque client
    # n'est appelé que si les précédents reviennent vides ET si sa clé est mise.
    # Clé vide -> client désactivé. NewsAPI/GNews : ~100 req/jour gratuites.
    newsapi_api_key: str = ""
    newsapi_url: str = "https://newsapi.org/v2/everything"
    newsapi_timeout: float = 20.0

    gnews_api_key: str = ""
    gnews_url: str = "https://gnews.io/api/v4/search"
    gnews_timeout: float = 20.0

    # Serper.dev (API Google). Clé gratuite : 2500 requêtes. En dernier recours.
    serper_api_key: str = ""
    serper_url: str = "https://google.serper.dev/search"
    serper_timeout: float = 20.0

    # --- Pipeline ---
    scan_default_interval_hours: int = 6
    max_queries_per_theme: int = 8
    max_results_per_query: int = 25
    max_articles_per_scan: int = 120
    llm_concurrency: int = 2
    http_timeout: float = 30.0
    scrape_timeout: float = 20.0

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
