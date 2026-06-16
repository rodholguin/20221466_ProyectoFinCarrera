"""R5 — Descarga de noticias (MediaCloud) + clasificación de sentimiento (Ollama).

Pasos:
  1. Para cada activo del universo, descarga noticias de MediaCloud (fetch_stories)
     y guarda data/raw/news_<TICKER>.parquet.
  2. Clasifica cada noticia con Ollama gemma3:4b y acumula un score diario.
  3. Guarda data/interim/sentiment_<TICKER>.parquet con esquema canónico.

Variables de entorno requeridas:
  MEDIACLOUD_API_TOKEN — token de la API v4.

Uso:
  python scripts/run_r5_news.py [--fetch-only] [--classify-only] [--ticker CREDITC1]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.universe import Config, SENTIMENT_SCHEMA
from src.sentiment.mediacloud_client import fetch_stories
from src.sentiment.llm_sentiment import classify_dataframe, aggregate_daily


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="R5: noticias + sentimiento")
    p.add_argument("--fetch-only", action="store_true",
                   help="Solo descarga noticias, no clasifica")
    p.add_argument("--classify-only", action="store_true",
                   help="Solo clasifica (asume parquets de noticias ya descargados)")
    p.add_argument("--ticker", default=None,
                   help="Procesar solo este ticker (ej: ALICORC1)")
    return p.parse_args()


def fetch_phase(cfg: Config, assets, raw_dir: Path) -> None:
    token = os.environ.get("MEDIACLOUD_API_TOKEN", "")
    if not token:
        print("ERROR: define MEDIACLOUD_API_TOKEN antes de ejecutar.")
        sys.exit(1)

    collection_id = cfg.sources["sentiment"]["peru_national_collection_id"]
    print(f"Colección MediaCloud: {collection_id}")

    for asset in assets:
        out = raw_dir / f"news_{asset.bvl}.parquet"
        if out.exists():
            print(f"  {asset.bvl}: ya existe {out.name}, saltando descarga.")
            continue
        print(f"  {asset.bvl}: descargando noticias {cfg.start} → {cfg.end} ...")
        allowlist = cfg.sources["sentiment"].get("source_allowlist")
        df = fetch_stories(asset, collection_id, cfg.start, cfg.end, raw_dir,
                           source_allowlist=allowlist)
        print(f"  {asset.bvl}: {len(df)} noticias guardadas en {out.name}")


def classify_phase(cfg: Config, assets, raw_dir: Path, interim_dir: Path) -> None:
    model = cfg.sources["sentiment"].get("llm_model", "gemma3:4b")
    cache_dir = interim_dir / "sentiment_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    interim_dir.mkdir(parents=True, exist_ok=True)

    print(f"Modelo Ollama: {model}")

    for asset in assets:
        news_path = raw_dir / f"news_{asset.bvl}.parquet"
        if not news_path.exists():
            print(f"  {asset.bvl}: sin noticias descargadas, saltando.")
            continue

        news = pd.read_parquet(news_path)
        if news.empty:
            print(f"  {asset.bvl}: DataFrame vacío, saltando.")
            continue

        print(f"  {asset.bvl}: clasificando {len(news)} noticias con {model} ...")
        cache_path = cache_dir / f"cache_{asset.bvl}.json"
        scored = classify_dataframe(news, asset.name, cache_path, model)
        daily = aggregate_daily(scored, how=cfg.sources["sentiment"].get("daily_aggregation", "mean"))

        out = interim_dir / f"sentiment_{asset.bvl}.parquet"
        daily[SENTIMENT_SCHEMA].to_parquet(out, index=False)
        print(f"  {asset.bvl}: {len(daily)} días de sentimiento → {out.name}")


def main() -> None:
    args = parse_args()
    cfg = Config.load(ROOT / "config.yaml")

    assets = cfg.assets
    if args.ticker:
        assets = [a for a in assets if a.bvl == args.ticker]
        if not assets:
            print(f"Ticker {args.ticker!r} no encontrado en el universo.")
            sys.exit(1)

    raw_dir     = ROOT / cfg.paths["raw"]
    interim_dir = ROOT / cfg.paths["interim"]

    if not args.classify_only:
        print("=== Fase 1: descarga de noticias (MediaCloud) ===")
        fetch_phase(cfg, assets, raw_dir)

    if not args.fetch_only:
        print("\n=== Fase 2: clasificación de sentimiento (Ollama) ===")
        classify_phase(cfg, assets, raw_dir, interim_dir)

    print("\nR5 completado.")


if __name__ == "__main__":
    main()
