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

    raw_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(raw_dir / f"news_{asset.bvl}.parquet")
    return df


def _build_query(asset: Asset) -> str:
    """Query booleana por emisor con términos de anclaje financiero.

    Los términos ambiguos (Buenaventura, Falabella) se anclan con AND a
    vocabulario económico para evitar capturar: la ciudad colombiana de
    Buenaventura, el jugador de fútbol, la cadena Falabella de Chile, etc.
    """
    _FINANCIAL = (
        "(accion OR acciones OR bolsa OR BVL OR utilidad OR inversion"
        " OR mercado OR empresa OR minera OR produccion OR resultado OR ganancia)"
    )
    aliases = {
        # BCP es sigla común; se ancla con términos bancarios/financieros
        "CREDITC1": (
            '(BCP OR Credicorp OR "Banco de Credito del Peru") AND '
            + _FINANCIAL
        ),
        # "Buenaventura" sola captura la ciudad colombiana y jugadores de fútbol
        "BUENAVC1": (
            '("Minas Buenaventura" OR "Compañia de Minas Buenaventura") AND '
            + _FINANCIAL
        ),
        # Alicorp es suficientemente específico; ancle suave para evitar notas triviales
        "ALICORC1": f'Alicorp AND {_FINANCIAL}',
        # "Falabella" sola captura la cadena chilena; "Saga" la acota a Perú
        "SAGAC1":   (
            '"Saga Falabella" AND ' + _FINANCIAL
        ),
        "CORAREC1": '"Aceros Arequipa"',
    }
    return aliases.get(asset.bvl, f'"{asset.name}"')


def _filter_by_source(df: pd.DataFrame, allowlist: list[str]) -> pd.DataFrame:
    """Filtra filas cuyo dominio (extraído de `url`) no está en el allowlist."""
    allowed = {d.lower().lstrip("www.") for d in allowlist}

    def _domain(url: str) -> str:
        try:
            netloc = urlparse(str(url)).netloc.lower()
            return netloc.lstrip("www.")
        except Exception:
            return ""

    mask = df["url"].apply(_domain).isin(allowed)
    return df[mask].reset_index(drop=True)


if __name__ == "__main__":
    if not _TOKEN:
        print("Define MEDIACLOUD_API_TOKEN para usar este módulo.")
    else:
        print("Colecciones que contienen 'Peru':")
        for c in find_peru_collection():
            print(f"  id={c['id']:>10}  {c['name']}")
        print("\nCopia el id de la colección NACIONAL a "
              "config.yaml -> sources.sentiment.peru_national_collection_id")
