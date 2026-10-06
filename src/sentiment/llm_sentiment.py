"""R5 (tareas 2.7) — Clasificación de noticias por TAXONOMÍA DE EVENTOS + score diario.

PROMPT v2 (2026-08-18). Reemplaza al v1 (polaridad libre con score continuo),
invalidado por la validación de julio: relevancia 26%, kappa 0.32 y 49% de las
etiquetas con signo provenientes de noticias que no hablaban de la empresa.
Especificación: docs/taxonomia_eventos_R5.txt · Decisión: D11.

QUÉ CAMBIA RESPECTO DE v1
  * El modelo clasifica el TIPO de evento (tarea objetiva) en vez de juzgar
    importancia. La magnitud la fija el autor por categoría (auditable).
  * La polaridad solo aplica a categorías de magnitud > 0, y se FUERZA en código
    (taxonomia.normaliza), no se confía en el prompt.
  * Un fallo de parseo ya NO se degrada a "neutral": se marca como _error_parseo
    y se cuenta. En v1 contaminaba en silencio.
  * El caché se indexa por (artículo, versión de prompt, modelo). Antes bumpear
    PROMPT_VERSION no invalidaba nada y se reusaban etiquetas viejas sin aviso.
  * Salida en dos niveles: por ARTÍCULO (fuente de verdad, permite recalibrar
    magnitudes o probar el esquema por tramos de D12 sin re-pagar el LLM) y
    agregada por día (lo que consume R6).
  * temperature=0 y format=json: reproducibilidad y menos fallos de parseo.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from src.sentiment import llm_backends
from src.sentiment.emisores import nombra_empresa
from src.sentiment.taxonomia import (
    CATEGORIAS, ERROR, PASA, POLARIDADES, bloque_categorias_prompt,
    es_relevante, magnitud, normaliza, prefiltro,
)

PROMPT_VERSION = "v2.1"
_POLARIDAD_VALOR = {"positivo": 1.0, "neutral": 0.0, "negativo": -1.0}

# D15: dos tramos de magnitud, no tres. ALTO = 1.0, RESTO = 0.6 y 0.3. Es el
# brazo de ablación pre-registrado; el brazo base suma los dos tramos.
# La celda `alto x positivo` tiene 39 eventos en 14 años y 7 activos, sostenida
# por n=2 filas de la muestra: por eso NO se abren tres tramos.
TRAMOS = ("alto", "resto")
_POL_ABREV = {"positivo": "pos", "neutral": "neu", "negativo": "neg"}

# v2.1 (2026-08-18) — reescrito tras el Piloto A. El modelo era sobre-inclusivo
# (precisión de relevancia 46.3%): nunca usaba `no_relevante` (0 predicciones) y
# volcaba todo lo dudoso en `sector_macro`. Los cambios atacan eso:
#   * la PREGUNTA DE FILTRO va PRIMERO y es binaria — es más fácil que elegir
#     entre 15 opciones, y es la decisión que de verdad importa;
#   * regla explícita de duda -> GRUPO B (antes el sesgo era al revés);
#   * caso del tipo de cambio nombrado, que explicaba 18 de los 19 errores de
#     CREDITC1 y es el 23% de su corpus (no es sobreajuste a la muestra).
_SYSTEM_PROMPT = (
    "Eres un analista financiero peruano. Recibes el TITULAR de una noticia y el "
    "nombre de una empresa que cotiza en la Bolsa de Valores de Lima.\n\n"
    "PASO 1 — LA PREGUNTA CLAVE. ¿El titular informa un HECHO CONCRETO DE ESA "
    "EMPRESA?\n"
    "  Un hecho concreto es algo que le pasó A LA EMPRESA: sus resultados, una "
    "compra, una inversión, una crisis, una norma que la afecta.\n"
    "  NO es un hecho de la empresa: que se la nombre como dato o ejemplo, que se "
    "hable de su sector, que aparezca en una crónica de la bolsa, o una nota de "
    "publicidad.\n"
    "  Si la respuesta es NO, elige del GRUPO B. Si dudas, elige GRUPO B.\n\n"
    "PASO 2. Elige UNA categoría:\n\n"
    + bloque_categorias_prompt() +
    "\n\nPASO 3. Solo si elegiste GRUPO A, indica la polaridad (positivo, "
    "negativo o neutral) según el impacto esperado en el valor de la acción de "
    'ESA empresa. Si elegiste GRUPO B, responde "no_aplica".\n\n'
    "REGLAS:\n"
    "- ANTE LA DUDA sobre si el titular trata de la empresa, usa "
    "mencion_incidental. Es preferible descartar una noticia buena que inventar "
    "un hecho que no está en el titular.\n"
    "- Una nota sobre el TIPO DE CAMBIO, la inflación o indicadores del mercado "
    "que cita a la empresa como fuente o referencia es mencion_incidental, NO un "
    "hecho de la empresa.\n"
    "- Una crónica del cierre de la bolsa es indice_bursatil, aunque nombre a la "
    "empresa con su porcentaje.\n"
    "- sector_macro es solo cuando se habla del sector o del precio de un insumo "
    "SIN un hecho de la empresa. Si el titular no trata del sector, NO uses esta "
    "categoría: usa mencion_incidental o no_relevante.\n"
    "- NO inventes una polaridad para justificar una etiqueta.\n"
    "- Responde SOLO JSON, sin explicación:\n"
    '{"categoria": "<una de la lista>", "polaridad": '
    '"<positivo|negativo|neutral|no_aplica>"}'
)


def classify_article(title: str, company: str, model: str = "gemma3:4b",
                     timeout: int = 180) -> dict:
    """Clasifica un titular. Devuelve {'categoria', 'polaridad'} ya normalizados.

    Funciona igual con modelos locales (Ollama) y comerciales (Gemini): el
    backend se elige por el nombre del modelo, y el prompt, la normalización y
    el parseo son idénticos para que la comparación del piloto sea válida.

    MediaCloud no entrega el cuerpo del artículo (verificado: la columna `text`
    no existe), así que la clasificación es por TITULAR. La anotación humana de
    referencia se hizo con esa MISMA información, así que la tarea es alcanzable
    desde el titular — ver docs/seleccion_modelo_R5.txt §4B.
    """
    crudo = llm_backends.call(
        _SYSTEM_PROMPT, f"Empresa: {company}\nTitular: {title}", model, timeout)
    return _parse(crudo)


def _parse(raw: str) -> dict:
    """Extrae {categoria, polaridad} del texto del modelo.

    A diferencia de v1, un fallo NO se convierte en una etiqueta plausible: se
    devuelve ERROR para poder contarlo y excluirlo de las features.
    """
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not m:
            return {"categoria": ERROR, "polaridad": None}
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return {"categoria": ERROR, "polaridad": None}

    if not isinstance(data, dict):
        return {"categoria": ERROR, "polaridad": None}
    cat, pol = normaliza(data.get("categoria"), data.get("polaridad"))
    return {"categoria": cat, "polaridad": pol}


def _clave(id_articulo: str, model: str) -> str:
    """Clave de caché versionada.

    Incluir prompt y modelo permite que v1 y v2 —y distintos modelos— coexistan
    sin pisarse, que es lo que hace posible comparar modelos en el piloto. En v1
    la clave era solo el id: bumpear la versión no invalidaba nada.
    """
    return f"{id_articulo}|{PROMPT_VERSION}|{model}"


def classify_dataframe(news: pd.DataFrame, company: str, cache_path: Path,
                       model: str = "gemma3:4b", save_every: int = 50,
                       usar_prefiltro: bool = True,
                       verbose: bool = True) -> tuple[pd.DataFrame, dict]:
    """Clasifica un DataFrame de noticias. Devuelve (artículos, estadísticas).

    El PREFILTRO se aplica antes del LLM: los titulares inequívocamente de índice
    o de patrocinio se etiquetan sin gastar una llamada (~12 s cada una). Ver la
    asimetría de costos en taxonomia.prefiltro.
    """
    cache = _load_cache(cache_path)
    total = len(news)
    filas, sin_guardar = [], 0
    n_pref = n_llm = n_cache = n_err = 0

    for i, (_, row) in enumerate(news.iterrows()):
        id_art = str(row.get("id") or row.get("url"))
        titulo = str(row.get("title") or "")

        cat_pref = prefiltro(titulo) if usar_prefiltro else PASA
        if cat_pref != PASA:
            res, origen = {"categoria": cat_pref, "polaridad": None}, "prefiltro"
            n_pref += 1
        else:
            k = _clave(id_art, model)
            if k in cache:
                res, origen = cache[k], "cache"
                n_cache += 1
            else:
                res = classify_article(titulo, company, model)
                cache[k] = res
                origen = "llm"
                n_llm += 1
                sin_guardar += 1
                if sin_guardar >= save_every:
                    _save_cache(cache_path, cache)
                    sin_guardar = 0
        if res["categoria"] == ERROR:
            n_err += 1

        filas.append({
            "id": id_art,
            "ticker": row.get("ticker"),
            "publish_date": row.get("publish_date"),
            "title": titulo,
            "categoria": res["categoria"],
            "polaridad": res["polaridad"],
            "magnitud": magnitud(res["categoria"]),
            "relevante": int(es_relevante(res["categoria"])),
            # D17: bandera DETERMINISTA (regex, sin LLM). NO filtra nada acá —
            # la restricción del canal se decide en R6 y es brazo de ablación
            # en R8. Se emite a nivel de ARTÍCULO porque ese es el nivel donde
            # la salida es fuente de verdad y se puede recalibrar sin re-pagar
            # el LLM (mismo principio que D11).
            "titular_nombra_empresa": int(
                nombra_empresa(str(row.get("ticker") or ""), titulo)),
            "origen": origen,
        })
        if verbose and ((i + 1) % save_every == 0 or (i + 1) == total):
            print(f"    [{i + 1}/{total}] {company}  "
                  f"(prefiltro {n_pref} · llm {n_llm} · caché {n_cache})", flush=True)

    _save_cache(cache_path, cache)
    stats = {"total": total, "prefiltro": n_pref, "llm": n_llm, "cache": n_cache,
             "errores_parseo": n_err,
             "tasa_error": (n_err / total) if total else 0.0}
    return pd.DataFrame(filas), stats


def aggregate_daily(art: pd.DataFrame) -> pd.DataFrame:
    """Agrega los artículos a un score diario por activo.

    Emite el insumo de las EWMAs de R6 (magnitud acumulada por SIGNO) y también
    el desglose por TRAMO de magnitud, que es lo que deja abierta la opción de
    D12 (pesos de tramo aprendidos) sin volver a llamar al LLM.

    `sentiment_score` se conserva por continuidad con el panel actual, pero se
    calcula SOLO sobre artículos relevantes: es la versión limpia del score de v1.

    D15 — CONTEOS POR CELDA, NO MAGNITUD ACUMULADA. La magnitud dejó de ser un
    multiplicador y quedó SOLO como puerta de relevancia: cada evento relevante
    pesa 1. Se emiten conteos `n_{tramo}_{polaridad}` con `neutral` INCLUIDO
    (antes `mag_pos`/`mag_neg` lo mandaban a 0 por construcción). De estos
    conteos R6 construye las 9 columnas `sent_{pos,neu,neg}_ewma_{5,20,60}`.
    Dos tramos, no tres: ALTO (magnitud 1.0) y RESTO (0.6 y 0.3). Es el brazo de
    ablación pre-registrado de 18 columnas; las 9 del brazo base salen de sumar
    los tramos, así que no hace falta emitirlas aparte.

    D17 — TODO SE EMITE POR DUPLICADO, con sufijo `_nom` para el subconjunto
    cuyo TITULAR nombra a la empresa. Es lo que permite construir el brazo
    RESTRINGIDO de la ablación de R8 sin volver al nivel de artículo. Acá NO se
    filtra nada: las columnas sin sufijo siguen agregando el corpus completo.
    """
    d = art.copy()
    d = d[d.categoria != ERROR]
    d["date"] = pd.to_datetime(d["publish_date"]).dt.date
    d["valor"] = d["polaridad"].map(_POLARIDAD_VALOR).fillna(0.0)
    # Corridas anteriores a D17 no traen la columna: se degrada a 0 (todo
    # anónimo) en vez de reventar, y el aviso queda en el `source`.
    if "titular_nombra_empresa" not in d.columns:
        d["titular_nombra_empresa"] = 0
    d["_nom"] = d["titular_nombra_empresa"].fillna(0).astype(int)
    d["_rel_nom"] = d["_nom"] * d["relevante"]

    # Dos tramos (D15): ALTO = magnitud 1.0, RESTO = 0.6 y 0.3. Los de magnitud
    # 0 no llegan acá: son la abstención y `relevante` ya los excluye.
    d["tramo"] = np.where(d["magnitud"] >= 1.0, "alto", "resto")

    base = (d.groupby(["ticker", "date"])
             .agg(n_articles=("id", "size"),
                  n_relevantes=("relevante", "sum"),
                  n_articles_nom=("_nom", "sum"),
                  n_relevantes_nom=("_rel_nom", "sum"))
             .reset_index())

    # Score continuo limpio: media de polaridad SOLO entre relevantes.
    # Se conserva por continuidad con el panel actual; NO es el insumo de D15.
    rel = d[d.relevante == 1]
    sc = (rel.groupby(["ticker", "date"])["valor"].mean()
             .rename("sentiment_score").reset_index())
    out = base.merge(sc, on=["ticker", "date"], how="left")
    out["sentiment_score"] = out["sentiment_score"].fillna(0.0)

    # Conteos por celda tramo x polaridad, con `neutral` incluido (D15), y
    # duplicados para el estrato de titular que nombra (D17).
    for tr in TRAMOS:
        for pol in POLARIDADES:
            sub = rel[(rel.tramo == tr) & (rel.polaridad == pol)]
            for suf, filtro in (("", sub), ("_nom", sub[sub._nom == 1])):
                col = f"n_{tr}_{_POL_ABREV[pol]}{suf}"
                g = (filtro.groupby(["ticker", "date"]).size()
                           .rename(col).reset_index())
                out = out.merge(g, on=["ticker", "date"], how="left")
                out[col] = out[col].fillna(0).astype(int)

    out["source"] = f"llm:{PROMPT_VERSION}"
    return out


def _load_cache(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
