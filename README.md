# news.minervia.fr

Agrégateur de news auto-généré, inspiré de Google News. L'utilisateur définit
des **thèmes** ; un **LLM** (LiteLLM `IA`) extrapole chaque thème en requêtes
élargies ; **SearXNG** scanne le web ; le service scrape, dédupplique,
**clusterise et résume** les articles ; une SPA **Next.js** affiche un fil de
cartes groupées par sujet.

## Architecture

```
[Navigateur] --HTTPS--> [Traefik] --Host(news.minervia.fr)--> [web : Next.js]
                                          \--/api--> [api : FastAPI]
                                                       |   |   |
        SearXNG (search?format=json) <-----------------+   |   +--> LiteLLM "IA"
        PostgreSQL (news) <--------------------------------+        (extrapolation + résumé)
        APScheduler (scan périodique par thème)
```

Le service réutilise la stack `qwen_3.8_vnimanieAI` via le réseau Docker partagé
`mynetwork` : **SearXNG**, **LiteLLM** et **Traefik** existants.

## Prérequis (une seule fois)

1. Créer le réseau partagé :
   ```bash
   docker network create mynetwork
   ```
2. Dans `~/qwen_3.8_vnimanieAI/docker-compose.yml`, déclarer le réseau en externe :
   ```yaml
   networks:
     mynetwork:
       external: true
   ```
   puis relancer la stack qwen (`./scripts/launch-stack.sh`).
3. Configurer ce service :
   ```bash
   cp .env.example .env   # renseigner POSTGRES_PASSWORD, JWT_SECRET, LITELLM_MASTER_KEY
   ```

## Lancement

```bash
cd ~/news
docker compose up -d --build
```

Puis ouvrir `https://news.minervia.fr`, créer un compte et un thème.

## Développement

- Backend : `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`
- Frontend : `cd frontend && npm install && npm run dev`

## Structure

```
backend/   FastAPI + SQLAlchemy + APScheduler (pipeline de scan)
frontend/  Next.js (App Router) + Tailwind
```
