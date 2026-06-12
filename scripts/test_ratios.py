"""Prueba compute_ratios() con los datos SMV ya extraídos."""
import sys
sys.path.insert(0, ".")

from pathlib import Path
from src.universe import Config
from src.fundamentals.fundamentals_client import fetch_smv, compute_ratios

cfg = Config.load()
wsdl   = cfg.sources["fundamentals"]["smv_wsdl"]
cache  = Path("data/raw/smv_cache")
START, END = "2022-01-01", "2023-12-31"

all_dfs = []
for asset in cfg.assets:
    df = fetch_smv(asset, wsdl, start=START, end=END, cache_dir=cache)
    all_dfs.append(df)

import pandas as pd
fundamentals = pd.concat(all_dfs, ignore_index=True)
ratios = compute_ratios(fundamentals)

print(f"Ratios: {len(ratios)} filas, {ratios['ticker'].nunique()} empresas, "
      f"{ratios['period'].nunique()} periodos\n")

# Mostrar tabla completa, formateada
pd.set_option("display.float_format", "{:.4f}".format)
pd.set_option("display.max_columns", 10)
pd.set_option("display.width", 120)

for ticker, grp in ratios.groupby("ticker"):
    print(f"{'='*70}")
    print(f"  {ticker}")
    print(grp[["period", "currency", "roe", "roa",
               "net_margin", "debt_equity", "debt_ratio"]].to_string(index=False))
    print()
