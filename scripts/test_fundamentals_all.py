"""Verifica extracción de las 5 empresas del universo (2022-2023, usando caché)."""
import sys
sys.path.insert(0, ".")

from pathlib import Path
from src.universe import Config
from src.fundamentals.fundamentals_client import fetch_smv

cfg = Config.load()
wsdl = cfg.sources["fundamentals"]["smv_wsdl"]
cache = Path("data/raw/smv_cache")

START, END = "2022-01-01", "2023-12-31"

results = {}
for asset in cfg.assets:
    print(f"\n{'='*55}")
    print(f"{asset.name}  (RPJ={asset.smv_rpj})")
    df = fetch_smv(asset, wsdl, start=START, end=END, cache_dir=cache)
    if df.empty:
        print(f"  ERROR: sin datos")
        results[asset.bvl] = None
        continue
    results[asset.bvl] = df

    # Resumen
    info = df[df["account"].str.startswith("INFO_")]
    last = info[info["period"] == info["period"].max()]
    print(f"  Filas totales: {len(df)}, periodos: {df['period'].nunique()}, cuentas: {df['account'].nunique()}")
    print(f"  Moneda: {df['currency'].unique()}")
    print(f"  Ultimo periodo ({last['period'].iloc[0]}):")
    for _, row in last.iterrows():
        val = f"{row['value']:>15,.0f}" if row['value'] else "     N/A"
        print(f"    {row['account']:35} = {val} {row['currency']}")

print(f"\n{'='*55}")
print("RESUMEN FINAL:")
for ticker, df in results.items():
    if df is None:
        print(f"  {ticker:10} ERROR")
    else:
        print(f"  {ticker:10} OK  — {len(df):4} filas, {df['period'].nunique()} periodos, {df['account'].nunique()} cuentas")
