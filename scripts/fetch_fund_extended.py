"""Descarga fundamentales SMV 2010-2023 para los 5 activos del universo.

Las llamadas al WSDL se cachean en data/raw/smv_cache/.
El primer activo descarga ~160 archivos nuevos (2010-2019); los demás usan caché.
"""
import time
from pathlib import Path

from src.universe import Config
from src.fundamentals.fundamentals_client import fetch_smv

START = "2005-01-01"   # cubre el inicio de la data de mercado más antigua (BUENAVC1)
END   = "2025-12-31"   # intenta hasta fin de 2025; la SMV puede no tener 2024-2025 aún

cfg      = Config.load("config.yaml")
raw_dir  = Path(cfg.paths["raw"])
smv_wsdl = cfg.sources["fundamentals"]["smv_wsdl"]
cache    = raw_dir / "smv_cache"

t0_total = time.time()
for asset in cfg.assets:
    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"Activo: {asset.bvl} ({asset.name})")
    df = fetch_smv(asset, smv_wsdl, start=START, end=END, cache_dir=cache)
    elapsed = time.time() - t0

    if df.empty:
        print(f"  ADVERTENCIA: sin datos para {asset.bvl}")
        continue

    out = raw_dir / f"fund_{asset.bvl}_smv.parquet"
    df.to_parquet(out, index=False)
    print(f"  Guardado: {out.name}")
    print(f"  Filas={len(df)}  Periodos={df['period'].nunique()}  "
          f"Cuentas={df['account'].nunique()}  ({elapsed:.0f}s)")

print(f"\nTotal: {time.time()-t0_total:.0f}s")
