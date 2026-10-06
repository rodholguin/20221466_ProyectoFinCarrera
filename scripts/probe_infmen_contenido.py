"""Inspecciona QUE trae el Informe Bursatil Mensual de la BVL.

Objetivo concreto: saber si publica MONTO NEGOCIADO POR EMISOR (lo que
necesitamos para acotar la capacidad de OE1) y con que granularidad, y si el
formato es estable entre 2013 y 2025 (condicion para parsear 173 informes).

Uso: probe_infmen_contenido.py <pdf> [--buscar NEMONICO ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pdfplumber

NEMONICOS = ["FERREYC1", "CPACASC1", "MINSURI1", "INRETC1", "LUSURC1",
             "ALICORC1", "CREDITC1"]

# Encabezados que delatan una tabla util
_CLAVE = re.compile(
    r"(monto\s+negociado|montos\s+negociados|frecuencia\s+de\s+negociaci|"
    r"cantidad\s+negociada|n[uú]mero\s+de\s+operaciones|valores\s+m[aá]s\s+"
    r"negociados|capitalizaci[oó]n\s+burs[aá]til|liquidez)", re.I)


def main() -> None:
    pdf_path = Path(sys.argv[1])
    print(f"=== {pdf_path.name} ===\n")

    with pdfplumber.open(pdf_path) as pdf:
        n = len(pdf.pages)
        print(f"Paginas: {n}\n")

        # 1) indice de secciones: primera linea no vacia de cada pagina
        print("--- TITULO DE CADA PAGINA ---")
        titulos = []
        for i, page in enumerate(pdf.pages, 1):
            txt = page.extract_text() or ""
            lineas = [l.strip() for l in txt.split("\n") if l.strip()]
            t = lineas[0] if lineas else "(vacia)"
            # muchas paginas empiezan con el header del documento; tomar la 2a
            if len(lineas) > 1 and len(t) < 25:
                t = f"{t} | {lineas[1]}"
            titulos.append((i, t))
            print(f"  p{i:3d}  {t[:100]}")

        # 2) paginas con tablas de interes
        print("\n--- PAGINAS CON ENCABEZADOS DE NEGOCIACION ---")
        for i, page in enumerate(pdf.pages, 1):
            txt = page.extract_text() or ""
            for mm in _CLAVE.finditer(txt):
                ctx = txt[max(0, mm.start() - 60): mm.start() + 90].replace("\n", " / ")
                print(f"  p{i:3d}  ...{ctx}...")

        # 3) donde aparecen nuestros nemonicos
        print("\n--- PAGINAS DONDE APARECEN LOS ACTIVOS DEL UNIVERSO ---")
        for nem in NEMONICOS:
            pags = []
            for i, page in enumerate(pdf.pages, 1):
                if nem in (page.extract_text() or ""):
                    pags.append(i)
            print(f"  {nem:10s} -> paginas {pags if pags else 'NO APARECE'}")

        # 4) volcado de la primera pagina donde aparezca FERREYC1
        for i, page in enumerate(pdf.pages, 1):
            txt = page.extract_text() or ""
            if "FERREYC1" in txt:
                print(f"\n--- VOLCADO p{i} (primera con FERREYC1) ---")
                print(txt[:2500])
                tablas = page.extract_tables()
                print(f"\n  pdfplumber detecta {len(tablas)} tabla(s) en esta pagina")
                for t in tablas[:1]:
                    for fila in t[:12]:
                        print("   ", fila)
                break


if __name__ == "__main__":
    main()
