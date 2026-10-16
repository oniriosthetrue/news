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

    # --- Sync vers le VPS (miroir en lecture seule) ---
    # Le boîtier (moteur : recherche + LLM) pousse les résultats DÉJÀ résumés
    # vers le VPS via une API signée (HMAC). Le VPS, lui, n'a jamais besoin du
    # LLM : il ne fait que recevoir et afficher. Boîtier éteint -> le VPS sert
    # le dernier contenu reçu ; boîtier rallumé -> les scans reprennent et repoussent.
    #
    # Côté BOÎTIER : sync_enabled=true + sync_target_url + sync_shared_secret.
    # Côté VPS (miroir) : mirror_mode=true + sync_shared_secret (scheduler coupé).
    sync_enabled: bool = False
    sync_target_url: str = ""  # ex. https://news.minervia.fr (le /api/sync/import est ajouté)
    sync_shared_secret: str = ""  # même valeur des deux côtés (signature HMAC des payloads)
    sync_interval_minutes: int = 30  # push périodique en plus du push post-scan
    sync_timeout: float = 30.0
    # Miroir : instance en lecture seule -> pas d'ordonnanceur, endpoint d'import actif.
    mirror_mode: bool = False
    # --- Probe LLM temps réel (VPS -> boîtier) ---
    # Le miroir n'a pas de LiteLLM. Pour le badge « LLM on/off », il SONDE le
    # boîtier en direct (flux VPS -> boîtier, distinct du push news boîtier -> VPS).
    # Côté VPS uniquement. engine_probe_url = URL joignable du boîtier (IP NetBird
    # via Traefik), engine_probe_host = en-tête Host à envoyer pour le routage Traefik.
    # Vide -> pas de probe : on retombe sur le dernier état poussé (table engine_status).
    engine_probe_url: str = ""  # ex. http://100.73.55.66/api/sync/engine-status
    engine_probe_host: str = ""  # ex. news.minervia.fr
    engine_probe_timeout: float = 5.0
    # --- Relais des écritures thème (VPS -> boîtier) ---
    # Le miroir est en lecture seule : créer/scaner un thème sur le site public
    # doit être EXÉCUTÉ par le boîtier (seul à pouvoir scanner), qui repousse
    # ensuite le résultat. Côté VPS uniquement. Vide -> écritures thème locales
    # (désactivées en pratique car le miroir ne scanne pas).
    engine_command_url: str = ""  # ex. http://100.73.55.66/api/sync/theme-command

    # --- Pipeline ---
    scan_default_interval_hours: int = 6
    max_queries_per_theme: int = 16
    max_results_per_query: int = 25
    max_articles_per_scan: int = 120
    # Nombre max de clusters (sujets regroupe) retenus par scan = nb d'appels
    # LLM de resume. Regle independamment du nb de requetes.
    max_clusters_per_scan: int = 40
    llm_concurrency: int = 2
    http_timeout: float = 30.0
    scrape_timeout: float = 20.0

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
