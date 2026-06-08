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
from pathlib import Path

import pandas as pd

from src.universe import Asset

_TOKEN = os.environ.get("MEDIACLOUD_API_TOKEN", "")


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
                  raw_dir: Path) -> pd.DataFrame:
    """Descarga (paginando) las noticias del emisor dentro de la colección."""
    import mediacloud.api as mc

    search = mc.SearchApi(_TOKEN)
    query = _build_query(asset)
    start_d = dt.date.fromisoformat(start)
    end_d = dt.date.fromisoformat(end)

    stories, token, more = [], None, True
    while more:
        page, token = search.story_list(
            query,
            start_date=start_d,
            end_date=end_d,
            collection_ids=[collection_id],   # <-- requisito de la API
            pagination_token=token,
        )
        stories += page
        more = token is not None

    df = pd.DataFrame(stories)
    if not df.empty:
        df["ticker"] = asset.bvl
        raw_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(raw_dir / f"news_{asset.bvl}.parquet")
    return df


def _build_query(asset: Asset) -> str:
    """Query por emisor: nombre comercial + alias. Ajustar por activo."""
    aliases = {
        "CREDITC1": '"Banco de Credito" OR "BCP" OR "Credicorp"',
        "BUENAVC1": '"Buenaventura" OR "Minas Buenaventura"',
        "ALICORC1": '"Alicorp"',
        "SAGAC1": '"Saga Falabella" OR "Falabella"',
        "CORAREC1": '"Aceros Arequipa" OR "Corporacion Aceros Arequipa"',
    }
    return aliases.get(asset.bvl, f'"{asset.name}"')


if __name__ == "__main__":
    if not _TOKEN:
        print("Define MEDIACLOUD_API_TOKEN para usar este módulo.")
    else:
        print("Colecciones que contienen 'Peru':")
        for c in find_peru_collection():
            print(f"  id={c['id']:>10}  {c['name']}")
        print("\nCopia el id de la colección NACIONAL a "
              "config.yaml -> sources.sentiment.peru_national_collection_id")
