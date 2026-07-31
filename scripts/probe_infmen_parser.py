"""Parser POR TEXTO del Informe Bursatil Mensual de la BVL (tabla Renta Variable).

Hallazgo: la tabla tiene las MISMAS 20 columnas en 2013 y en 2025; lo unico que
cambia es que los PDF antiguos no traen lineas de tabla, asi que extract_tables
falla. Anclando en el ISIN (PE + 10 alfanumericos) la linea se parte igual en
ambas epocas:

  [acciones_circulacion, valor_nominal, capitalizacion, valor_contable(, M)]
  ISIN  NEMONICO(nota)
  [cantidad_negociada, monto_pen, monto_usd, pct_total, n_ope, frecuencia,
   apertura, cierre, maxima, minima, promedio, cmt, rotacion, rendim_mensual]

Uso: probe_infmen_parser.py <pdf> [<pdf> ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pdfplumber

NEMONICOS = ["FERREYC1", "CPACASC1", "MINSURI1", "INRETC1", "LUSURC1",
             "ALICORC1", "CREDITC1"]

# ISIN estandar: 2 letras de pais + 9 alfanumericos + digito de control.
# NO restringir a "PE": InRetail es un holding panameno y su ISIN empieza en PA.
_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
_NOTA = re.compile(r"^\(\d+([,\d]*)\)$")
_POST = ["cantidad_negociada", "monto_pen", "monto_usd", "pct_total", "n_ope",
         "frecuencia", "apertura", "cierre", "maxima", "minima", "promedio",
         "cmt", "rotacion", "rendim_mensual"]


def parse_linea(linea: str) -> dict | None:
    tok = linea.split()
    idx = next((i for i, t in enumerate(tok) if _ISIN.match(t)), None)
    if idx is None or idx + 1 >= len(tok):
        return None

    nem = tok[idx + 1]
    m = re.match(r"^([A-Z]{2,10}[A-Z0-9]\d)(\(.*\))?$", nem)
    if not m:
        return None
    nem = m.group(1)

    antes = [t for t in tok[:idx] if t != "M"]
    desp = [t for t in tok[idx + 2:] if not _NOTA.match(t)]

    reg: dict[str, str] = {"nemonico": nem, "isin": tok[idx]}
    for k, v in zip(["acciones_circulacion", "valor_nominal", "capitalizacion",
                     "valor_contable"], antes):
        reg[k] = v
    for k, v in zip(_POST, desp):
        reg[k] = v
    reg["_n_antes"], reg["_n_desp"] = len(antes), len(desp)
    return reg


def extrae(pdf_path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            up = txt.upper()
            if "RENTA VARIABLE" not in up:
                continue
            if re.search(r"ENERO\s*[-–]\s*\w+", txt, re.I):
                continue                      # acumulado semestral, otra tabla
            for linea in txt.split("\n"):
                reg = parse_linea(linea)
                if reg and reg["nemonico"] in NEMONICOS:
                    out.setdefault(reg["nemonico"], reg)
    return out


def main() -> None:
    for arg in sys.argv[1:]:
        p = Path(arg)
        print(f"\n{'=' * 96}\n=== {p.name} ===\n{'=' * 96}")
        datos = extrae(p)
        print(f"  extraidos {len(datos)}/{len(NEMONICOS)}\n")
        print(f"  {'activo':10s} {'acciones circ.':>16s} {'cant.negociada':>15s} "
              f"{'monto S/':>17s} {'N op':>6s} {'frec%':>7s} {'cierre':>9s} {'rot':>8s}")
        for nem in NEMONICOS:
            d = datos.get(nem)
            if not d:
                print(f"  {nem:10s} {'NO APARECE (no listado ese mes)':>16s}")
                continue
            print(f"  {nem:10s} {d.get('acciones_circulacion',''):>16s} "
                  f"{d.get('cantidad_negociada',''):>15s} {d.get('monto_pen',''):>17s} "
                  f"{d.get('n_ope',''):>6s} {d.get('frecuencia',''):>7s} "
                  f"{d.get('cierre',''):>9s} {d.get('rotacion',''):>8s}")
        anchos = {(d["_n_antes"], d["_n_desp"]) for d in datos.values()}
        print(f"\n  (anchos antes/despues del ISIN: {sorted(anchos)})")


if __name__ == "__main__":
    main()
