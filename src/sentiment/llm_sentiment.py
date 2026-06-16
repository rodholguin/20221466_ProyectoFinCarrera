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
import re
import urllib.request
from pathlib import Path

import pandas as pd

PROMPT_VERSION = "v1"
_LABELS = {"positivo": 1.0, "neutral": 0.0, "negativo": -1.0}
_OLLAMA_URL = "http://localhost:11434/api/chat"

_SYSTEM_PROMPT = (
    "Eres un analista financiero. Clasifica el sentimiento de la noticia sobre "
    "la empresa indicada en una de: positivo, negativo, neutral, según su "
    "impacto esperado en el valor de la acción. Responde SOLO JSON: "
    '{"sentiment": "<positivo|negativo|neutral>", "confidence": <0-1>}.'
)


def classify_article(title: str, text: str, company: str,
                     model: str = "gemma3:4b") -> dict:
    """Llama a Ollama y devuelve {'sentiment', 'confidence'}.

    Usa la API REST local de Ollama (http://localhost:11434).
    Requiere que el servicio esté corriendo: `ollama serve`.
    """
    user_content = f"Empresa: {company}\nTítulo: {title}\n{text[:2000]}"
    payload = json.dumps({
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
    }).encode()

    req = urllib.request.Request(
        _OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = json.loads(resp.read())

    raw = body["message"]["content"].strip()
    return _parse_llm_json(raw)


def _parse_llm_json(raw: str) -> dict:
    """Extrae el JSON del texto del LLM; tolera markdown code fences."""
    # quita ```json ... ``` si el modelo los añade
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # fallback: busca la primera llave JSON en el texto
        m = re.search(r"\{[^}]+\}", cleaned)
        if m:
            data = json.loads(m.group())
        else:
            return {"sentiment": "neutral", "confidence": 0.0}

    sentiment = str(data.get("sentiment", "neutral")).lower()
    if sentiment not in _LABELS:
        sentiment = "neutral"
    confidence = float(data.get("confidence", 0.5))
    return {"sentiment": sentiment, "confidence": confidence}


def classify_dataframe(news: pd.DataFrame, company: str, cache_path: Path,
                       model: str = "gemma3:4b",
                       save_every: int = 50) -> pd.DataFrame:
    """Clasifica un DataFrame de noticias con caché por id de noticia."""
    cache = _load_cache(cache_path)
    scores = []
    total = len(news)
    new_since_save = 0
    for i, (_, row) in enumerate(news.iterrows()):
        key = str(row.get("id") or row.get("url"))
        if key not in cache:
            title = str(row.get("title") or "")
            # MediaCloud story_list no devuelve texto completo; el campo puede
            # ser NaN, None o ausente. El clasificador trabaja principalmente
            # con el título, que sí viene siempre y es suficiente para
            # sentimiento financiero de corto plazo.
            raw_text = row.get("text")
            text = "" if (raw_text is None or pd.isna(raw_text)) else str(raw_text)
            res = classify_article(title, text, company, model)
            cache[key] = res
            new_since_save += 1
            if new_since_save >= save_every:
                _save_cache(cache_path, cache)
                new_since_save = 0
        scores.append(_LABELS[cache[key]["sentiment"]])
        if (i + 1) % save_every == 0 or (i + 1) == total:
            print(f"    [{i + 1}/{total}] {company}", flush=True)
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
