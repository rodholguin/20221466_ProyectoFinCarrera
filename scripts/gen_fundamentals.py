"""Genera parquets de fundamentales para todos los activos del universo.

Usa el caché SMV en data/raw/smv_cache/ para evitar re-descargar datos.
"""
from pathlib import Path
from src.universe import Config
from src.fundamentals.fundamentals_client import fetch_fundamentals

cfg = Config.load("config.yaml")

for asset in cfg.assets:
    p = Path("data/raw") / f"fund_{asset.bvl}_smv.parquet"
    if p.exists():
        import pandas as pd
        df_ex = pd.read_parquet(p)
        print(f"{asset.bvl}: ya existe ({len(df_ex)} filas)")
        continue
    print(f"\nGenerando {asset.bvl}...")
    df = fetch_fundamentals(
        asset, cfg.sources,
        start="2020-01-01", end="2023-12-31",
        raw_dir=Path("data/raw"),
    )
    if not df.empty:
        periodos = df["period"].nunique()
        cuentas  = df["account"].nunique()
        print(f"  -> {len(df)} filas, {periodos} periodos, {cuentas} cuentas")
    else:
        print(f"  -> SIN DATOS")
