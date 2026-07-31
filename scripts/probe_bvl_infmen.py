"""Verifica cobertura y contenido del INFORME BURSATIL MENSUAL de la BVL.

Patron de URL descubierto: documents.bvl.com.pe/pubdif/infmen/M{YYYY}_{MM}.pdf
Es la fuente OFICIAL candidata para montos negociados historicos por emisor
(el volumen de Yahoo resulto parcial; ver project_yahoo_volumen_confiabilidad).

1) Sondea HEAD sobre 2012-2025 para medir cobertura y tamaño.
2) Descarga 3 muestras (inicio / medio / fin del horizonte) al scratchpad.
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

BASE = "https://documents.bvl.com.pe/pubdif/infmen/M{y}_{m:02d}.pdf"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
DEST = Path(sys.argv[1] if len(sys.argv) > 1 else ".")


def head(y: int, m: int):
    url = BASE.format(y=y, m=m)
    try:
        r = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
        return r.status_code, int(r.headers.get("Content-Length") or 0)
    except Exception:
        return None, 0


def main() -> None:
    print("Cobertura de documents.bvl.com.pe/pubdif/infmen/M{YYYY}_{MM}.pdf\n")
    print(f"  {'año':>5s}  {'meses OK':>8s}  {'tamaño medio (KB)':>18s}  detalle")
    total = 0
    for y in range(2012, 2027):
        ok, sizes, faltan = 0, [], []
        for m in range(1, 13):
            code, size = head(y, m)
            if code == 200:
                ok += 1
                sizes.append(size)
            else:
                faltan.append(m)
        total += ok
        med = sum(sizes) / len(sizes) / 1024 if sizes else 0
        det = "completo" if ok == 12 else f"faltan meses {faltan}"
        print(f"  {y:5d}  {ok:8d}  {med:18.0f}  {det}")
    print(f"\n  TOTAL informes disponibles 2012-2026: {total}")

    # muestras
    DEST.mkdir(parents=True, exist_ok=True)
    for y, m in ((2013, 6), (2019, 6), (2025, 6)):
        url = BASE.format(y=y, m=m)
        r = requests.get(url, headers=HEADERS, timeout=60)
        if r.status_code != 200:
            print(f"  no se pudo bajar {url} ({r.status_code})")
            continue
        p = DEST / f"infmen_{y}_{m:02d}.pdf"
        p.write_bytes(r.content)
        print(f"  descargado {p}  ({len(r.content)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
