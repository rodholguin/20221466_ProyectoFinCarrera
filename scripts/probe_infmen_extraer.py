"""Prototipo de EXTRACCION del Informe Bursatil Mensual (tabla Renta Variable).

La tabla "Valores Negociados" trae, POR EMISOR Y POR MES:
  Acciones en Circulacion | Valor Nominal | Capitalizacion Bursatil | Valor Contable
  ISIN | Nemonico | Cantidad Negociada | Monto Efectivo S/ y US$ | % Total
  N Operaciones | FRECUENCIA (%) | Apertura/Cierre/Maxima/Minima/Promedio
  C.M.T. | Rotacion | Rendimiento mensual

Este script prueba si pdfplumber la parsea de forma ESTABLE en informes de
distintos años (condicion para automatizar los 173 informes 2012-2026) y
volcar las filas de los 7 activos del universo.

Uso: probe_infmen_extraer.py <pdf> [<pdf> ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pdfplumber

NEMONICOS = ["FERREYC1", "CPACASC1", "MINSURI1", "INRETC1", "LUSURC1",
             "ALICORC1", "CREDITC1"]

CAMPOS = ["acciones_circulacion", "valor_nominal", "capitalizacion", "valor_contable",
          "isin", "nemonico", "cantidad_negociada", "monto_pen", "monto_usd",
          "pct_total", "n_operaciones", "frecuencia_pct", "apertura", "cierre",
          "maxima", "minima", "promedio", "cmt", "rotacion", "rendim_mensual"]


def limpia(x: str | None) -> str:
    return (x or "").strip()


def es_fila_valor(fila: list) -> str | None:
    """Devuelve el nemonico si la fila corresponde a un valor listado."""
    for celda in fila[:8]:
        c = limpia(celda)
        # el nemonico puede venir con sufijos tipo AENZAC1(3)
        m = re.fullmatch(r"([A-Z]{2,10}[A-Z0-9]\d)(\(\d+\))?", c)
        if m:
            return m.group(1)
    return None


def extrae(pdf_path: Path) -> tuple[dict[str, dict], list[str]]:
    """Devuelve (filas por nemonico, encabezados crudos detectados).

    El encabezado de la seccion cambio entre años: 2025 usa
    "Renta Variable / Valores Negociados: <mes>" y 2013 usa
    "RENTA VARIABLE - <mes> EQUITIES". Se detecta por 'RENTA VARIABLE' y se
    EXCLUYE el acumulado semestral ('ENERO - <mes>'), que es otra tabla.
    """
    filas: dict[str, dict] = {}
    encabezados: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            if "RENTA VARIABLE" not in txt.upper():
                continue
            if re.search(r"ENERO\s*[-–]\s*\w+", txt, re.I):
                continue          # acumulado del anexo estadistico
            for tabla in page.extract_tables():
                for fila in tabla:
                    vals = [limpia(c) for c in fila]
                    # guardar el encabezado (fila con muchas etiquetas de texto)
                    txts = [v for v in vals if v and not re.match(r"^[\d.,$%\-]+$", v)]
                    if len(txts) >= 6 and not es_fila_valor(fila) and not encabezados:
                        encabezados = vals
                    nem = es_fila_valor(fila)
                    if nem not in NEMONICOS:
                        continue
                    reg = dict(zip(CAMPOS, vals))
                    reg["_ncols"] = len(vals)
                    reg["_crudo"] = vals
                    filas[nem] = reg
    return filas, encabezados


def main() -> None:
    for arg in sys.argv[1:]:
        p = Path(arg)
        print("\n" + "=" * 100)
        print(f"=== {p.name} ===")
        print("=" * 100)
        datos, enc = extrae(p)
        if not datos:
            print("  NADA extraido -> el formato de este año NO coincide con el parser")
            continue
        print(f"  extraidos {len(datos)}/{len(NEMONICOS)} activos "
              f"(ancho de fila: {sorted({d['_ncols'] for d in datos.values()})})")
        if enc:
            limpio = [e.replace("\n", " ") for e in enc if e]
            print(f"  ENCABEZADO detectado ({len(enc)} cols): {limpio}")
        ej = next(iter(datos.values()))
        print(f"  FILA CRUDA ejemplo: {ej['_crudo']}\n")
        for nem in NEMONICOS:
            d = datos.get(nem)
            if not d:
                print(f"  {nem:10s} NO APARECE (puede no estar listado ese año)")
                continue
            print(f"  {nem}")
            print(f"     acciones en circulacion : {d['acciones_circulacion']:>18s}"
                  f"   nominal {d['valor_nominal']}")
            print(f"     capitalizacion bursatil : {d['capitalizacion']:>18s}"
                  f"   valor contable {d['valor_contable']}")
            print(f"     CANTIDAD NEGOCIADA      : {d['cantidad_negociada']:>18s}"
                  f"   monto S/ {d['monto_pen']}  US$ {d['monto_usd']}")
            print(f"     N operaciones           : {d['n_operaciones']:>18s}"
                  f"   FRECUENCIA {d['frecuencia_pct']}%   rotacion {d['rotacion']}")
            print(f"     cotizaciones            : apertura {d['apertura']}  "
                  f"cierre {d['cierre']}  max {d['maxima']}  min {d['minima']}  "
                  f"prom {d['promedio']}")


if __name__ == "__main__":
    main()
