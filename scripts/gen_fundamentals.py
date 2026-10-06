"""Genera parquets de fundamentales para todos los activos del universo.

Usa el caché SMV en data/raw/smv_cache/ para evitar re-descargar datos: el
servicio de la SMV devuelve TODAS las empresas de un período en una llamada, así
que sumar activos al universo es casi gratis (solo cambia el RPJ que se filtra).

El tipo de EEFF (Individual/Consolidado) sale de config.yaml por activo
(`smv_tipo`; "C" en INRETC1, holding cuyo individual reporta pérdida).

Uso:  python scripts/gen_fundamentals.py           # respeta los parquets existentes
      python scripts/gen_fundamentals.py --force   # regenera todos
"""
from pathlib import Path
import sys

import pandas as pd

from src.universe import Config
from src.fundamentals.fundamentals_client import fetch_fundamentals

force = "--force" in sys.argv

cfg = Config.load("config.yaml")
raw_dir = Path(cfg.paths["raw"])

# Horizonte real del estudio (config.yaml period), no un rango de prueba: los
# EEFF de la SMV arrancan antes que el mercado (BVL 2012+) y el panel R6 los
# alinea por known_date.
START, END = cfg.start, cfg.end

for asset in cfg.assets:
    p = raw_dir / f"fund_{asset.bvl}_smv.parquet"
    if p.exists() and not force:
        df_ex = pd.read_parquet(p)
        print(f"{asset.bvl}: ya existe ({len(df_ex)} filas) -- usar --force para regenerar")
        continue
    print(f"\nGenerando {asset.bvl} (tipo={asset.smv_tipo or 'I'})...")
    df = fetch_fundamentals(
        asset, cfg.sources,
        start=START, end=END,
        raw_dir=raw_dir,
    )
    if not df.empty:
        periodos = df["period"].nunique()
        cuentas  = df["account"].nunique()
        print(f"  -> {len(df)} filas, {periodos} periodos, {cuentas} cuentas")
    else:
        print(f"  -> SIN DATOS")
