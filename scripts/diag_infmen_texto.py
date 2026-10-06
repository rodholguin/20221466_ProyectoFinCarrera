"""Vuelca lineas crudas de un informe para ver por que el parser no las reconoce.

Uso: diag_infmen_texto.py <YYYY-MM> <nemonico>
"""
from __future__ import annotations

import sys
from pathlib import Path

import pdfplumber

PDF_DIR = Path("data/raw/bvl_infmen")

arg, nem = sys.argv[1], sys.argv[2]
y, m = arg.split("-")
pdf = PDF_DIR / f"M{y}_{int(m):02d}.pdf"

with pdfplumber.open(pdf) as d:
    print(f"=== {pdf.name}: lineas que contienen '{nem}' ===\n")
    for i, pg in enumerate(d.pages, 1):
        txt = pg.extract_text() or ""
        for linea in txt.split("\n"):
            if nem in linea:
                print(f"  p{i:3d} | {linea[:230]}")
                print(f"        tokens: {linea.split()[:12]}")
                print()
