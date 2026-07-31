"""Diagnostica los huecos del panel mensual: meses sin fila y por que.

Tres informes no produjeron filas y cinco activos tienen 166 meses frente a los
171 de CREDITC1. Antes de usar el panel hay que saber si son ausencias REALES
(el valor no cotizo / no estaba listado) o fallos del parser.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.market import bvl_infmen
from src.universe import Config

PDF_DIR = Path("data/raw/bvl_infmen")


def main() -> None:
    cfg = Config.load("config.yaml")
    df = bvl_infmen.load_mensual()

    todos = pd.period_range("2012-01", "2026-06", freq="M")
    presentes = set(df["periodo"])
    faltan_panel = [p for p in todos if p not in presentes]

    print("=" * 78)
    print("A. MESES SIN NINGUNA FILA EN EL PANEL")
    print("=" * 78)
    for p in faltan_panel:
        pdf = PDF_DIR / f"M{p.year}_{p.month:02d}.pdf"
        if not pdf.exists():
            print(f"  {p}: NO se descargo el PDF")
            continue
        kb = pdf.stat().st_size / 1024
        # cuantas paginas y si hay texto extraible
        try:
            import pdfplumber
            with pdfplumber.open(pdf) as d:
                npag = len(d.pages)
                con_texto = sum(1 for pg in d.pages if (pg.extract_text() or "").strip())
                hay_rv = sum(1 for pg in d.pages
                             if "RENTA VARIABLE" in (pg.extract_text() or "").upper())
            print(f"  {p}: PDF {kb:.0f} KB, {npag} pags, {con_texto} con texto, "
                  f"{hay_rv} con 'RENTA VARIABLE'")
        except Exception as exc:
            print(f"  {p}: PDF {kb:.0f} KB pero no se pudo abrir ({exc})")

    print("\n" + "=" * 78)
    print("B. MESES FALTANTES POR ACTIVO DEL UNIVERSO")
    print("=" * 78)
    for asset in cfg.assets:
        sub = df[df["nemonico"] == asset.bvl]
        tiene = set(sub["periodo"])
        # solo desde su primera aparicion (evita contar meses previos al listado)
        if not tiene:
            print(f"  {asset.bvl}: SIN datos")
            continue
        desde = min(tiene)
        esperados = [p for p in todos if p >= desde and p in presentes]
        faltan = [p for p in esperados if p not in tiene]
        print(f"  {asset.bvl:10s} desde {desde}  faltan {len(faltan)}: "
              f"{[str(x) for x in faltan][:12]}")

    print("\n" + "=" * 78)
    print("C. SANIDAD DE LOS DATOS DEL UNIVERSO")
    print("=" * 78)
    for asset in cfg.assets:
        sub = bvl_infmen.panel_activo(asset.bvl, df)
        acc = sub["acciones_circulacion"].dropna()
        mon = sub["monto_pen"].dropna()
        frec = sub["frecuencia"].dropna()
        print(f"  {asset.bvl:10s} acciones {acc.min():>15,.0f}..{acc.max():>15,.0f} "
              f"| monto/mes S/ {mon.median():>13,.0f} | frec {frec.min():5.1f}"
              f"..{frec.max():5.1f}% (mediana {frec.median():5.1f})")


if __name__ == "__main__":
    main()
