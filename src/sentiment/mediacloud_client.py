"""R5 (tareas 2.6–2.7) — Recopilación de noticias con Media Cloud.

Resuelve TU pregunta concreta: `story_list` EXIGE `collection_ids` o `sources`.
Aquí:
  1. `find_peru_collection()` usa el DirectoryApi para obtener el id de la
     colección nacional de Perú (guárdalo luego en config.yaml).
  2. `fetch_stories()` consulta por emisor acotando con esa colección.
  3. Opcionalmente, `list_peru_sources()` lista los medios de esa colección
     por si prefieres acotar con `sources=[...]` (más preciso, menos ruido).

Token: variable de entorno MEDIACLOUD_API_TOKEN.
Instalar: pip install mediacloud
"""
from __future__ import annotations

import datetime as dt
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from src.universe import Asset

_TOKEN = os.environ.get("MEDIACLOUD_API_TOKEN", "")
_PAGE_DELAY  = 1.0   # segundos entre páginas (evita rate limiting)
_RETRY_MAX   = 5
_RETRY_DELAY = 10.0  # segundos de espera inicial ante error de API


def find_peru_collection(name: str = "Peru") -> list[dict]:
    """Devuelve colecciones cuyo nombre contiene `name`. Toma la 'national'."""
    import mediacloud.api as mc

    directory = mc.DirectoryApi(_TOKEN)
    res = directory.collection_list(name=name)
    return res.get("results", [])


def list_peru_sources(collection_id: int) -> list[dict]:
    """Lista (paginando) los medios dentro de una colección, por si quieres
    filtrar con `sources` en vez de toda la colección nacional."""
    import mediacloud.api as mc

    directory = mc.DirectoryApi(_TOKEN)
    sources, offset, limit = [], 0, 100
    while True:
        resp = directory.source_list(collection_id=collection_id,
                                     limit=limit, offset=offset)
        sources += resp["results"]
        if resp.get("next") is None:
            break
        offset += limit
    return sources


def fetch_stories(asset: Asset, collection_id: int, start: str, end: str,
                  raw_dir: Path,
                  source_allowlist: list[str] | None = None) -> pd.DataFrame:
    """Descarga (paginando) las noticias del emisor dentro de la colección.

    Incluye retry exponencial ante errores transitorios de la API y pausa
    entre páginas para no superar el rate limit.

    `source_allowlist`: dominios permitidos (ej. ["gestion.pe", "elcomercio.pe"]).
    Si se provee, se descartan artículos de fuentes no incluidas en la lista,
    eliminando tabloides, medios deportivos y fuentes extranjeras que se
    cuelan en la colección nacional de MediaCloud.
    """
    import mediacloud.api as mc

    search = mc.SearchApi(_TOKEN)
    query = _build_query(asset)
    start_d = dt.date.fromisoformat(start)
    end_d = dt.date.fromisoformat(end)

    stories, token, more, page_n = [], None, True, 0
    while more:
        page_n += 1
        for attempt in range(1, _RETRY_MAX + 1):
            try:
                page, token = search.story_list(
                    query,
                    start_date=start_d,
                    end_date=end_d,
                    collection_ids=[collection_id],
                    pagination_token=token,
                )
                break
            except Exception as exc:
                wait = _RETRY_DELAY * (2 ** (attempt - 1))
                print(f"    [pág {page_n} intento {attempt}/{_RETRY_MAX}] error: {exc} — "
                      f"esperando {wait:.0f}s ...")
                if attempt == _RETRY_MAX:
                    raise
                time.sleep(wait)
        stories += page
        more = token is not None
        if more:
            time.sleep(_PAGE_DELAY)

    df = pd.DataFrame(stories)
    if df.empty:
        return df

    df["ticker"] = asset.bvl

    if source_allowlist:
        before = len(df)
        df = _filter_by_source(df, source_allowlist)
        print(f"    filtro de fuentes: {before} → {len(df)} noticias")

    before = len(df)
    df = deduplicar(df)
    print(f"    deduplicación:     {before} → {len(df)} noticias "
          f"({(before-len(df))/max(before,1):.1%} sindicación)")

    # PROVENANCE: sin esto no hay forma de distinguir un corpus bajado con la
    # query v1 de uno con la v2 una vez guardado en disco.
    df["query"] = query
    df["fetched_at"] = pd.Timestamp.utcnow().isoformat()

    raw_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(raw_dir / f"news_{asset.bvl}.parquet")
    return df


def _build_query(asset: Asset) -> str:
    """Query booleana por emisor. SOLO desambigua el NOMBRE, no filtra relevancia.

    CAMBIO v2 (2026-08-18) — SE ELIMINÓ EL ANCLA `_FINANCIAL`. Estaba MEDIDO que
    era contraproducente: sus términos (bolsa, BVL, accion, mercado, empresa) son
    el vocabulario de las CRÓNICAS DE ÍNDICE, así que admitía preferentemente el
    ruido y rechazaba la señal. Sobre los titulares de CORAREC1 (el único activo
    descargado sin ancla) dejaba pasar "La bolsa limeña perdió 0,25%" y bloqueaba
    "Aceros Arequipa adquiere activos en Florida" (M&A, magnitud 1.0) e "Indecopi
    suprime derechos antidumping contra alambrón chino" (regulatorio, 1.0).
    Evidencia: docs/taxonomia_eventos_R5.txt §7.2.

    ASIMETRÍA QUE ORDENA EL DISEÑO: un irrelevante que entra cuesta ~12 s de LLM y
    la taxonomía lo manda a magnitud 0; un relevante que no se descarga se pierde
    para siempre. La query maximiza RECALL; la precisión la resuelven el prefiltro
    (costo) y la taxonomía (corrección). Ver §7.5.

    La desambiguación de nombre sí se conserva donde el nombre es ambiguo:
    Pacasmayo es también provincia y ciudad; BCP es sigla de varias cosas.
    """
    aliases = {
        "CREDITC1": '"Banco de Credito del Peru" OR Credicorp OR '
                    '(BCP AND (banco OR financiero))',
        "MINSURI1": '"Minsur"',
        "ALICORC1": '"Alicorp"',
        # Marcas comerciales: es donde vive la noticia real de InRetail. Generan
        # ruido de marketing, que la categoría `marketing_promocion` absorbe.
        "INRETC1":  '"InRetail" OR "Supermercados Peruanos" OR "Plaza Vea" '
                    'OR "InkaFarma"',
        # "Pacasmayo" solo es también provincia/ciudad -> se acota con contexto.
        "CPACASC1": '"Cementos Pacasmayo" OR (Pacasmayo AND (cemento OR cementera '
                    'OR planta))',
        "FERREYC1": '"Ferreycorp" OR "Ferreyros"',
        "LUSURC1":  '"Luz del Sur"',
        # Universo viejo (se conservan para poder reproducir corridas anteriores).
        "BUENAVC1": '"Minas Buenaventura" OR "Compañia de Minas Buenaventura"',
        "SAGAC1":   '"Saga Falabella"',
        "CORAREC1": '"Aceros Arequipa" OR "Corporacion Aceros Arequipa"',
    }
    if asset.bvl not in aliases:
        raise ValueError(
            f"{asset.bvl} no tiene query definida en _build_query. Antes caía en "
            f'un default \'"{asset.name}"\' que para razones sociales poco usadas '
            "en prensa (p. ej. 'InRetail Peru Corp') devolvía casi nada y habría "
            "invalidado el corpus en silencio. Definir la query explícitamente.")
    return aliases[asset.bvl]


def deduplicar(df: pd.DataFrame, ventana_dias: int = 2) -> pd.DataFrame:
    """Quita duplicados por sindicación: mismo titular en una ventana de días.

    Medido sobre el corpus actual: 12.2% en CORAREC1, 10.6% en BUENAVC1, 5.0% en
    ALICORC1. Se usa una VENTANA y no la fecha exacta porque la sindicación cruza
    días (dup por título 13.5% vs 12.2% por título+fecha en CORAREC1).
    """
    if df.empty or "title" not in df.columns:
        return df
    d = df.copy()
    d["_t"] = d["title"].astype(str).str.strip().str.lower()
    d["_f"] = pd.to_datetime(d["publish_date"]).dt.normalize()
    d = d.sort_values(["_t", "_f"])
    # Dentro de cada titular, marca como duplicado si el anterior está a <= ventana
    delta = d.groupby("_t")["_f"].diff().dt.days
    d["_dup"] = (delta.notna()) & (delta <= ventana_dias)
    out = d[~d["_dup"]].drop(columns=["_t", "_f", "_dup"])
    return out.sort_index()


def _quita_www(netloc: str) -> str:
    """Quita el prefijo 'www.' — con removeprefix, NO con lstrip.

    BUG CORREGIDO (2026-08-18): `lstrip("www.")` quita CARACTERES del conjunto
    {w, .}, no el prefijo. Un dominio que empiece con 'w' perdía esa letra
    ('wapa.pe' -> 'apa.pe'). Con el allowlist actual (gestion/elcomercio/
    larepublica) era latente —verificado: 0 dominios afectados— pero rompería en
    cuanto se agregue un medio con 'w' inicial.
    """
    return netloc.removeprefix("www.")


def _filter_by_source(df: pd.DataFrame, allowlist: list[str]) -> pd.DataFrame:
    """Filtra filas cuyo dominio (extraído de `url`) no está en el allowlist.

    Acepta SUBDOMINIOS del dominio permitido (m.gestion.pe cuenta como
    gestion.pe): antes se descartaban en silencio, perdiendo las versiones
    móviles.
    """
    allowed = {_quita_www(d.lower()) for d in allowlist}

    def _permitido(url: str) -> bool:
        try:
            host = _quita_www(urlparse(str(url)).netloc.lower())
        except Exception:
            return False
        return any(host == a or host.endswith("." + a) for a in allowed)

    return df[df["url"].apply(_permitido)].reset_index(drop=True)


if __name__ == "__main__":
    if not _TOKEN:
        print("Define MEDIACLOUD_API_TOKEN para usar este módulo.")
    else:
        print("Colecciones que contienen 'Peru':")
        for c in find_peru_collection():
            print(f"  id={c['id']:>10}  {c['name']}")
        print("\nCopia el id de la colección NACIONAL a "
              "config.yaml -> sources.sentiment.peru_national_collection_id")
