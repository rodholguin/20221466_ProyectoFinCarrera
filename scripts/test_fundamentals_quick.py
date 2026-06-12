"""Test rápido: extrae 2 años de fundamentales de Alicorp desde el SMV."""
import sys
sys.path.insert(0, ".")

from pathlib import Path
from src.universe import Config
from src.fundamentals.fundamentals_client import fetch_smv

cfg = Config.load()
alicorp = next(a for a in cfg.assets if a.bvl == "ALICORC1")
wsdl = cfg.sources["fundamentals"]["smv_wsdl"]
cache = Path("data/raw/smv_cache")

print(f"Activo: {alicorp.name}  RPJ={alicorp.smv_rpj}")
df = fetch_smv(alicorp, wsdl, start="2022-01-01", end="2023-12-31", cache_dir=cache)

if df.empty:
    print("ERROR: sin datos")
    sys.exit(1)

print(f"\nResultado: {len(df)} filas, {df['period'].nunique()} periodos")
print(f"Periodos: {sorted(df['period'].unique())}")
print(f"Cuentas ({df['account'].nunique()} únicas):")
for acc in sorted(df['account'].unique())[:30]:
    print(f"  {acc}")
print(f"\nMuestra:")
print(df[df["account"].str.startswith("INFO")].to_string(index=False))
