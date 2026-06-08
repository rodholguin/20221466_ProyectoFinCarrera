"""R5 (tareas 2.7) — Clasificación de sentimiento vía LLM + score diario.

Clasificación zero-shot (positivo/negativo/neutral) por noticia con un LLM
vía API, luego agregación a un score diario por activo (alineado al cierre).

Buenas prácticas incluidas:
  * prompt versionado (PROMPT_VERSION) para reproducibilidad,
  * salida estructurada (JSON),
  * caché por noticia (evita re-pagar el LLM),
  * cuidado con zona horaria al fijar el corte diario.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROMPT_VERSION = "v1"
_LABELS = {"positivo": 1.0, "neutral": 0.0, "negativo": -1.0}

_SYSTEM_PROMPT = (
    "Eres un analista financiero. Clasifica el sentimiento de la noticia sobre "
    "la empresa indicada en una de: positivo, negativo, neutral, según su "
    "impacto esperado en el valor de la acción. Responde SOLO JSON: "
    '{"sentiment": "<positivo|negativo|neutral>", "confidence": <0-1>}.'
)


def classify_article(title: str, text: str, company: str,
                     provider: str = "anthropic") -> dict:
    """Llama al LLM y devuelve {'sentiment','confidence'}.

    TODO: cablear el proveedor real. Ejemplo Anthropic:

        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-...", max_tokens=100,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user",
                       "content": f"Empresa: {company}\\n{title}\\n{text[:2000]}"}])
        return json.loads(msg.content[0].text)
    """
    raise NotImplementedError("Conectar proveedor LLM (anthropic/google/openai).")


def classify_dataframe(news: pd.DataFrame, company: str, cache_path: Path,
                       provider: str = "anthropic") -> pd.DataFrame:
    """Clasifica un DataFrame de noticias con caché por id de noticia."""
    cache = _load_cache(cache_path)
    scores = []
    for _, row in news.iterrows():
        key = str(row.get("id") or row.get("url"))
        if key not in cache:
            res = classify_article(row.get("title", ""), row.get("text", ""),
                                   company, provider)
            cache[key] = res
        scores.append(_LABELS[cache[key]["sentiment"]])
    _save_cache(cache_path, cache)
    out = news.copy()
    out["sentiment_score"] = scores
    return out


def aggregate_daily(scored: pd.DataFrame, how: str = "mean") -> pd.DataFrame:
    """Score diario por activo. `date` debe ser la fecha de publicación local."""
    scored = scored.copy()
    scored["date"] = pd.to_datetime(scored["publish_date"]).dt.date
    agg = (scored.groupby(["ticker", "date"])
                 .agg(sentiment_score=("sentiment_score", how),
                      n_articles=("sentiment_score", "size"))
                 .reset_index())
    agg["source"] = f"llm:{PROMPT_VERSION}"
    return agg


def _load_cache(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
