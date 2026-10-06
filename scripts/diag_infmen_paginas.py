"""Por que ciertos informes no produjeron filas (o solo las primeras).

Casos: 2016-03, 2019-03 y 2024-09 dieron 0 filas; en 2021-01..2021-05 solo salio
CREDITC1 (que esta en la PRIMERA pagina de la tabla, seccion bancos), lo que
apunta a que las paginas siguientes fueron descartadas por algun filtro.

Muestra, pagina por pagina: si tiene 'RENTA VARIABLE', si el filtro de acumulado
la descarto y por que, y cuantas filas parsea.

Uso: diag_infmen_paginas.py <YYYY-MM> [<YYYY-MM> ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pdfplumber

from src.market.bvl_infmen import _ACUMULADO, _parse_linea

PDF_DIR = Path("data/raw/bvl_infmen")
UNIV = {"FERREYC1", "CPACASC1", "MINSURI1", "INRETC1", "LUSURC1",
        "ALICORC1", "CREDITC1"}


def main() -> None:
    for arg in sys.argv[1:]:
        y, m = arg.split("-")
        pdf = PDF_DIR / f"M{y}_{int(m):02d}.pdf"
        print("\n" + "=" * 84)
        print(f"=== {arg}  ({pdf.name}) ===")
        print("=" * 84)
        if not pdf.exists():
            print("  no existe")
            continue

        with pdfplumber.open(pdf) as d:
            for i, pg in enumerate(d.pages, 1):
                txt = pg.extract_text() or ""
                if "RENTA VARIABLE" not in txt.upper():
                    continue
                mm = _ACUMULADO.search(txt)
                filas = [_parse_linea(l) for l in txt.split("\n")]
                filas = [f for f in filas if f]
                nuestros = sorted({f["nemonico"] for f in filas} & UNIV)
                estado = f"DESCARTADA por acumulado ('{mm.group(0)}')" if mm else "usada"
                cab = txt.split("\n")[0][:60]
                print(f"  p{i:3d} {estado:38s} filas={len(filas):3d} "
                      f"univ={nuestros}")
                if mm and len(filas) > 3:
                    print(f"       cabecera: {cab}")
                    ctx = txt[max(0, mm.start()-70): mm.start()+40].replace("\n", " / ")
                    print(f"       contexto del match: ...{ctx}...")


if __name__ == "__main__":
    main()
