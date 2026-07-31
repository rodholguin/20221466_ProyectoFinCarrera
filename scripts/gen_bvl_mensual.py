"""Descarga y parsea los Informes Bursátiles Mensuales de la BVL -> parquet.

Genera data/interim/bvl_mensual.parquet con una fila por (mes, nemónico) y las
20 columnas oficiales de negociación. Es la fuente OFICIAL de volumen, monto
negociado, frecuencia de negociación y acciones en circulación; reemplaza a
Yahoo, que se descartó como cantidad autoritativa (ver src/market/bvl_infmen.py).

Uso:
    python scripts/gen_bvl_mensual.py                 # 2012-2026, con caché
    python scripts/gen_bvl_mensual.py --refresh       # reparsea los PDF
    python scripts/gen_bvl_mensual.py --force-download

OJO DISCO: son ~173 PDF de 0.6-2.4 MB => ~250 MB en data/raw/bvl_infmen/.
"""
from __future__ import annotations

import argparse

import pandas as pd

from src.market import bvl_infmen
from src.universe import Config


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="reparsea los PDF aunque exista el parquet")
    ap.add_argument("--force-download", action="store_true",
                    help="vuelve a descargar los PDF aunque estén en disco")
    ap.add_argument("--start-year", type=int, default=2012)
    ap.add_argument("--end-year", type=int, default=2026)
    args = ap.parse_args()

    cfg = Config.load("config.yaml")
    universo = [a.bvl for a in cfg.assets]

    df = bvl_infmen.load_mensual(
        refresh=args.refresh or args.force_download,
        start_year=args.start_year, end_year=args.end_year,
        force_download=args.force_download)

    if df.empty:
        print("Sin datos: no se pudo construir el panel mensual.")
        return

    print("\n" + "=" * 78)
    print(f"PANEL MENSUAL BVL: {len(df):,} filas  |  "
          f"{df['nemonico'].nunique():,} valores  |  "
          f"{df['periodo'].nunique()} meses "
          f"({df['periodo'].min()} .. {df['periodo'].max()})")
    print("=" * 78)

    faltan = sorted(set(pd.period_range(df["periodo"].min(), df["periodo"].max(),
                                        freq="M")) - set(df["periodo"]))
    print(f"  meses sin informe: {[str(p) for p in faltan] or 'ninguno'}")

    print("\n  Cobertura del universo (meses con fila):")
    for nem in universo:
        sub = df[df["nemonico"] == nem]
        if sub.empty:
            print(f"    {nem:10s} SIN DATOS")
            continue
        con_neg = int(sub["cantidad_negociada"].notna().sum())
        print(f"    {nem:10s} {len(sub):4d} meses "
              f"({sub['periodo'].min()} .. {sub['periodo'].max()})  "
              f"con negociación: {con_neg:4d}")

    print(f"\n  Guardado en {bvl_infmen._CACHE}")


if __name__ == "__main__":
    main()
