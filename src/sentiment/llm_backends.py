"""Backends de inferencia para R5. Un modelo, dos proveedores.

El piloto compara modelos locales (Ollama) contra comerciales sobre la MISMA
muestra anotada, así que el prompt, el prefiltro y las métricas deben ser
idénticos y lo único que cambia es quién responde. Este módulo aísla esa
diferencia: ambas funciones reciben (system, user) y devuelven el texto crudo
del modelo, que `llm_sentiment._parse` normaliza igual en los dos casos.

El despacho es por nombre de modelo: "gemini-*" va a Google, todo lo demás a
Ollama. Así `--model` sigue siendo el único parámetro que hay que cambiar.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from src.sentiment.taxonomia import CATEGORIAS, POLARIDADES

_OLLAMA_URL = os.environ.get(
    "OLLAMA_URL", "http://localhost:11434").rstrip("/") + "/api/chat"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

# Esquema estricto: el proveedor GARANTIZA que `categoria` sea una de las 15 y
# `polaridad` una de las 4. Con Ollama solo se puede pedir "JSON válido" y hay
# que validar la categoría a mano (de ahí los `_error_parseo` por categoría
# inventada). Aquí ese modo de falla no existe.
_SCHEMA = {
    "type": "object",
    "properties": {
        "categoria": {"type": "string", "enum": list(CATEGORIAS)},
        "polaridad": {"type": "string",
                      "enum": [*POLARIDADES, "no_aplica"]},
    },
    "required": ["categoria", "polaridad"],
}


def es_gemini(model: str) -> bool:
    return model.lower().startswith("gemini")


def _post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # El cuerpo del error trae el motivo real (cuota, key inválida, modelo
        # inexistente). Sin esto solo se ve "HTTP 400" y no se puede diagnosticar.
        detalle = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"HTTP {e.code} de {url}: {detalle}") from None


def call_ollama(system: str, user: str, model: str, timeout: int = 180) -> str:
    body = _post(
        _OLLAMA_URL,
        {"model": model, "stream": False, "format": "json",
         "options": {"temperature": 0},
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]},
        {"Content-Type": "application/json"},
        timeout)
    return body["message"]["content"].strip()


def call_gemini(system: str, user: str, model: str, timeout: int = 180) -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            "Define GEMINI_API_KEY (se obtiene en aistudio.google.com/apikey)")
    body = _post(
        _GEMINI_URL,
        {"model": model,
         "input": user,
         "system_instruction": system,
         "generation_config": {"temperature": 0},
         "response_format": {"type": "text",
                             "mime_type": "application/json",
                             "schema": _SCHEMA}},
        {"Content-Type": "application/json", "x-goog-api-key": key},
        timeout)
    txt = body.get("output_text")
    if txt:
        return txt.strip()
    # Ruta manual, por si la propiedad de conveniencia no viene en la respuesta.
    try:
        return body["steps"][-1]["content"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(
            f"Respuesta de Gemini sin texto reconocible: "
            f"{json.dumps(body)[:400]}") from None


def call(system: str, user: str, model: str, timeout: int = 180) -> str:
    """Despacha al proveedor según el nombre del modelo."""
    return (call_gemini if es_gemini(model) else call_ollama)(
        system, user, model, timeout)
