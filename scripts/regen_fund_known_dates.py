"""Regenera los parquets de fundamentales con known_date = fecha REAL de
presentación (BVL Hechos de Importancia) cuando existe, con fallback al lag fijo.

Usa el caché SMV (data/raw/smv_cache) para los EEFF y cachea los hechos de
importancia de la BVL por emisor. Sobrescribe fund_{ticker}_smv.parquet.

Uso:  python scripts/regen_fund_known_dates.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.universe import Config
from src.fundamentals.fundamentals_client import fetch_fundamentals

START, END = "2005-01-01", "2025-12-31"


def main() -> None:
    cfg = Config.load(ROOT / "config.yaml")
    raw_dir = ROOT / cfg.paths["raw"]
    for asset in cfg.assets:
        print(f"\n{'='*60}\nRegenerando fundamentales: {asset.bvl}")
        df = fetch_fundamentals(asset, cfg.sources, start=START, end=END,
                                raw_dir=raw_dir)
        if not df.empty:
            print(f"  -> {len(df)} filas, {df['period'].nunique()} periodos, "
                  f"known_date {df['known_date'].min()}..{df['known_date'].max()}")
        else:
            print("  -> SIN DATOS")


if __name__ == "__main__":
    main()
