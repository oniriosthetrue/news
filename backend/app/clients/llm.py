"""Client LiteLLM (OpenAI-compatible) pour l'extrapolation de thèmes et les résumés.

Le déploiement émet parfois le préambule de raisonnement dans `delta["reasoning"]`
(voir mémoire vllm-streaming) — ici on consomme des réponses NON stream, donc on lit
simplement `choices[0].message.content`.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMError(RuntimeError):
    pass


async def online(client: httpx.AsyncClient) -> bool:
    """Le LLM (LiteLLM) est-il joignable ? Vrai si /models répond 200.

    Utilisé par l'indicateur « LLM on/off » de l'UI. Court timeout : on ne veut
    pas bloquer l'affichage de la page si la passerelle est éteinte (ex. miroir
    VPS sans LiteLLM, ou boîtier hors ligne).
    """
    try:
        resp = await client.get(
            f"{settings.litellm_base_url}/models",
            headers={"Authorization": f"Bearer {settings.litellm_api_key}"},
            timeout=4.0,
        )
    except httpx.HTTPError:
        return False
    return resp.status_code == 200


async def _chat(
    client: httpx.AsyncClient,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.4,
    max_tokens: int = 1024,
) -> str:
    payload = {
        "model": settings.litellm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {settings.litellm_api_key}"}
    resp = await client.post(
        f"{settings.litellm_base_url}/chat/completions",
        json=payload,
        headers=headers,
        timeout=settings.http_timeout,
    )
    if resp.status_code != 200:
        raise LLMError(f"LiteLLM {resp.status_code}: {resp.text[:300]}")
    data: dict[str, Any] = resp.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as exc:
        raise LLMError(f"Réponse LLM inattendue: {data}") from exc


def _extract_json(text: str) -> Any:
    """Extrait le premier objet/tableau JSON d'une réponse LLM (tolère le bruit)."""
    text = text.strip()
    # Retire les fences ```json ... ```
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Repli : première portion {...} ou [...]
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError(f"JSON introuvable dans la réponse LLM: {text[:200]}")


async def extrapolate_queries(
    client: httpx.AsyncClient,
    theme_name: str,
    description: str,
    max_queries: int,
    context: Optional[str] = None,
) -> list[str]:
    """Thème -> liste de requêtes de recherche élargies (synonymes, entités, sous-sujets).

    Si `context` est fourni (titres d'articles réellement trouvés sur le web),
    le LLM s'y ANCRE pour extraire les acteurs/sous-sujets d'actualité au lieu
    de puiser dans sa connaissance d'entraînement (qui peut etre perimee).
    """
    system = (
        "Tu élargis un thème d'actualité en requêtes de recherche web variées et "
        "complémentaires, destinées à couvrir un MAXIMUM d'articles de presse. "
        "Mélange obligatoirement les angles : (1) le sujet central et ses synonymes, "
        "(2) l'actualité récente et les derniers développements, (3) les acteurs "
        "cités dans les journaux (personnalités, partis, institutions, entreprises), "
        "(4) les réactions, débats et controverses. Ne te limite PAS aux aspects "
        "techniques ou chiffrés : prévois des requêtes « grand public » et "
        "politiques telles qu'un lecteur les taperait. "
        "Quand des titres d'articles réels sont fournis, PRIORISE les acteurs, "
        "entités et angles qu'ils mentionnent explicitement. "
        "Réponds UNIQUEMENT par un tableau JSON de chaînes, sans texte autour."
    )
    user = (
        f"Thème : {theme_name}\n"
        f"Description : {description or '(aucune)'}\n"
    )
    if context:
        user += (
            f"\nTitres d'articles récents trouvés sur ce thème (source d'ancrage) :\n"
            f"{context}\n"
        )
    user += (
        f"\nProduis au plus {max_queries} requêtes de recherche en français, courtes, "
        f"spécifiques et non redondantes, couvrant les angles ci-dessus. "
        f"Format : [\"...\", \"...\"]"
    )
    raw = await _chat(client, [{"role": "system", "content": system},
                               {"role": "user", "content": user}], temperature=0.6)
    data = _extract_json(raw)
    if not isinstance(data, list):
        raise LLMError("La réponse d'extrapolation n'est pas une liste")
    queries = [str(q).strip() for q in data if str(q).strip()]
    # Dédup + borne
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            out.append(q[:400])
        if len(out) >= max_queries:
            break
    return out


async def summarize_cluster(
    client: httpx.AsyncClient, theme_name: str, items: list[dict[str, str]]
) -> tuple[str, str]:
    """Regroupe des articles similaires -> (titre de cluster, résumé 2-3 phrases)."""
    system = (
        "Tu es un rédacteur d'agrégateur de news. À partir d'articles sur le même "
        "sujet, produis un titre neutre et factuel et un résumé concis (2-3 phrases) "
        "qui synthétise l'information commune. "
        'Réponds UNIQUEMENT par un objet JSON {"title": "...", "summary": "..."}.'
    )
    lines = "\n".join(
        f"- [{it.get('source', '?')}] {it.get('title', '')}: "
        f"{(it.get('snippet') or it.get('content') or '')[:400]}"
        for it in items
    )
    user = f"Thème : {theme_name}\nArticles :\n{lines}"
    raw = await _chat(client, [{"role": "system", "content": system},
                               {"role": "user", "content": user}], temperature=0.3,
                      max_tokens=512)
    data = _extract_json(raw)
    if not isinstance(data, dict):
        raise LLMError("Résumé LLM inattendu")
    return str(data.get("title", "")).strip(), str(data.get("summary", "")).strip()
