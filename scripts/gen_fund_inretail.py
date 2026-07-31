"""Descarga los fundamentales CONSOLIDADOS de InRetail y verifica el calendario
de acciones por tramos (item (c) del handoff de universo).

Es también el paso R4 de ese activo: escribe data/raw/fund_INRETC1_smv.parquet y
deja la caché SMV de tipo "C" lista para el resto de la corrida.

START = 2012 y NO cfg.start (2005) A PROPÓSITO: InRetail Peru Corp hizo su IPO en
oct-2012 y su primer EEFF en el SMV es 2012Q4, así que los 30 períodos 2005-2011
serían descargas puras de descarte. Y no son gratis: el WSDL devuelve TODAS las
empresas por período/operación (~5 MB por archivo), y el tipo "C" no está cacheado
de corridas anteriores (el universo viejo solo usaba "I"). Para el resto del
universo, que usa tipo "I", la caché 2005-2025 ya existe -> ahí sí es casi gratis.

Uso:  python scripts/gen_fund_inretail.py [YYYY-MM-DD]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.universe import Config
from src.fundamentals.fundamentals_client import compute_ratios, fetch_fundamentals


def main() -> None:
    cfg = Config.load(ROOT / "config.yaml")
    asset = [a for a in cfg.assets if a.bvl == "INRETC1"][0]
    start = sys.argv[1] if len(sys.argv) > 1 else "2012-01-01"
    print(f"[gen_fund_inretail] {start} -> {cfg.end} (tipo={asset.smv_tipo})")

    df = fetch_fundamentals(asset, cfg.sources, start=start, end=cfg.end,
                            raw_dir=ROOT / cfg.paths["raw"])
    if df.empty:
        print("SIN DATOS")
        return
    print(f"\n{len(df)} filas, {df['period'].nunique()} periodos, "
          f"monedas {df['currency'].unique().tolist()}")

    r = compute_ratios(df, asset=asset)
    cols = [c for c in ("period", "known_date", "shares_outstanding",
                        "net_income_ttm", "eps_ttm", "roe") if c in r.columns]
    r = r[cols].dropna(subset=["shares_outstanding"])

    print("\n--- alrededor del follow-on 2022-Q2 ---")
    print(r[(r["period"] >= "2021-09-30") & (r["period"] <= "2023-03-31")].to_string(index=False))

    print("\n--- tramos del conteo ---")
    print(r.groupby("shares_outstanding")["period"].agg(["min", "max", "count"]).to_string())

    # Impacto de (c): EPS con el calendario vs con el override único anterior
    pre = r[r["period"] < "2022-06-30"].copy()
    if not pre.empty and pre["eps_ttm"].notna().any():
        eps_old = pre["net_income_ttm"] * 1000.0 / 108746887.0
        rel = (pre["eps_ttm"] / eps_old - 1.0).dropna()
        print(f"\nEPS pre-2022Q2: el calendario lo sube {rel.mean():+.2%} en promedio "
              f"(min {rel.min():+.2%}, max {rel.max():+.2%}) vs el override único "
              f"-> el P/E baja en la misma proporción.")
    out = ROOT / "data" / "interim" / "check_inretail_shares.csv"
    r.to_csv(out, index=False)
    print("detalle ->", out)


if __name__ == "__main__":
    main()
