"""Vuelca el texto crudo de la tabla de renta variable en un informe ANTIGUO,
para decidir si se parsea por texto (regex por linea) en vez de extract_tables.

Uso: probe_infmen_2013_pagina.py <pdf> <pagina>
"""
from __future__ import annotations

import sys
from pathlib import Path

import pdfplumber

p = Path(sys.argv[1])
npag = int(sys.argv[2])

with pdfplumber.open(p) as pdf:
    page = pdf.pages[npag - 1]
    print(f"=== {p.name} pagina {npag} ===\n")
    print("--- TEXTO ---")
    print((page.extract_text() or "")[:4000])
    print("\n--- extract_tables ---")
    ts = page.extract_tables()
    print(f"{len(ts)} tabla(s)")
    for t in ts[:2]:
        for fila in t[:8]:
            print("   ", fila)
