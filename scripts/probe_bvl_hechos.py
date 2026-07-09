"""Sondeo BVL — Hechos de Importancia / EEFF trimestrales con fecha (RESUELTO jul-2026).

Objetivo: obtener la FECHA REAL de presentación de cada EEFF intermedio ante el
mercado, para reemplazar/validar el lag fijo de known_date (45d Q1-Q3 / 60d Q4).

RESUELTO. El endpoint POST /v1/corporate-actions ("Hechos de Importancia") SÍ
sirve. El bloqueo previo ('Regex string must not be null!', 500) era por un
payload equivocado (companyCode/text/dateInit...). El payload correcto se capturó
del propio frontend Angular de la BVL (bvl.com.pe -> detalle emisor -> pestaña
"Hechos de importancia", request XHR interceptado):

    POST https://dataondemand.bvl.com.pe/v1/corporate-actions
    {"rpjCode": "B30006", "page": 1, "size": 15,
     "search": "", "startDate": "2026-06-01", "endDate": "2026-07-31"}

  - Se identifica por rpjCode (NO companyCode ni nemónico). startDate/endDate son
    fechas OBLIGATORIAS yyyy-MM-dd (el 500 'text' era LocalDate.parse(null)).
  - Respuesta paginada: {totalElements, totalPages, first, last, content[]}.
  - Cada item: registerDate (TIMESTAMP REAL de registro ante el mercado <- la
    fecha que buscábamos), sessionDate, businessName, observation, session,
    documents[{sequence, path->PDF}], codes[{codeHHII, descCodeHHII}].

HALLAZGO CLAVE — validado en los 5 emisores × 6 trimestres (30 puntos), usando el
EEFF INTERMEDIO INDIVIDUAL ("Información Financiera Intermedia Individual al ...",
que es el Tipo=I que consume el pipeline). Las fechas reales de presentación son
SIEMPRE anteriores al lag fijo actual (45d Q1-Q3 / 60d Q4): holgura mínima global
= 0 días => NO hay look-ahead en ningún caso. Pero el margen varía mucho por
emisor: bancos/mineras presentan mucho antes del deadline.
    emisor    lag real (rango)   holgura vs modelo   comentario
    CREDITC1  +19..+26 d         +19..+36 d          BCP presenta ~3-5 sem antes
    CORAREC1  +18..+25 d         +20..+37 d          idem, muy temprano
    ALICORC1  +29..+46 d         +13..+16 d          conservador ~2 sem
    SAGAC1    +30..+46 d         +13..+15 d          idem
    BUENAVC1  +26..+60 d         +0..+19 d           Q4 JUSTO en +60 (regla NYSE)
Conclusión: el known_date por lag fijo es causalmente seguro (no filtra), pero
demora los fundamentales hasta ~5 semanas (peor en CREDITC1/CORAREC1). El Q4 de
BUENAVC1 cae exactamente en +60d => confirma que la corrección Q4->60d era
necesaria (un +45d ahí sería -14d de look-ahead). Con este endpoint se puede
reemplazar el lag por la fecha de presentación REAL (registerDate), con fallback
al lag fijo cuando no exista el hecho.
"""
from __future__ import annotations
import re
from datetime import date, datetime

import requests

DOD = "https://dataondemand.bvl.com.pe"
H = {"User-Agent": "Mozilla/5.0 Chrome/120", "Origin": "https://www.bvl.com.pe",
     "Referer": "https://www.bvl.com.pe/", "Accept": "application/json, text/plain, */*",
     "Content-Type": "application/json"}

# rpjCode por nemónico (== código SMV; ver docs/hallazgos_fundamentales_R4.txt §3
# y config.yaml smv_rpj). El endpoint BVL acepta el mismo código.
RPJ = {
    "CREDITC1": "B80005", "BUENAVC1": "B20003", "ALICORC1": "B30006",
    "SAGAC1": "014313", "CORAREC1": "CI0003",
}
_MODEL_LAG = {1: 45, 2: 45, 3: 45, 4: 60}
_MON = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7,
        "ago": 8, "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12}
_Q = {3: 1, 6: 2, 9: 3, 12: 4}  # mes de fin-de-trimestre -> trimestre


def fetch_facts(rpj: str, start: str, end: str, size: int = 100) -> list[dict]:
    """Devuelve TODOS los hechos de importancia del emisor en [start, end]."""
    out: list[dict] = []
    page = 1
    while True:
        body = {"rpjCode": rpj, "page": page, "size": size,
                "search": "", "startDate": start, "endDate": end}
        j = requests.post(DOD + "/v1/corporate-actions", headers=H,
                          json=body, timeout=40).json()
        out += j.get("content", [])
        if j.get("last") or page >= j.get("totalPages", 1):
            break
        page += 1
    return out


def _parse_quarter(obs: str) -> tuple[date, int] | None:
    """De 'Intermedia Individual al 31-Mar-2024' -> (fin_trim, trimestre)."""
    m = re.search(r"al\s+(\d{1,2})-([A-Za-z]{3})-(\d{4})", obs)
    if not m:
        return None
    d, mon, y = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    if mon not in _MON or _MON[mon] not in _Q:
        return None
    return date(y, _MON[mon], d), _Q[_MON[mon]]


def filing_dates(rpj: str, start: str, end: str) -> dict[tuple[int, int], date]:
    """Mapa (ejercicio, trimestre) -> fecha REAL de presentación del EEFF
    intermedio INDIVIDUAL (Tipo=I), a partir de registerDate."""
    out: dict[tuple[int, int], date] = {}
    for f in fetch_facts(rpj, start, end):
        obs = (f.get("observation") or "")
        if "intermedia individual" not in obs.lower():
            continue
        parsed = _parse_quarter(obs)
        if not parsed:
            continue
        qend, q = parsed
        reg = datetime.strptime(f["registerDate"].split()[0], "%Y-%m-%d").date()
        out[(qend.year, q)] = reg  # el más reciente gana si hubiera re-presentación
    return out


if __name__ == "__main__":
    print(f"{'emisor':9} {'fin_trim':11} Q {'real':11} {'lag_r':>5} {'lag_m':>5} {'holg':>5}")
    worst = 99
    for nemo, rpj in RPJ.items():
        fd = filing_dates(rpj, "2022-12-01", "2024-06-30")
        for (yy, q), reg in sorted(fd.items()):
            qend = {1: date(yy, 3, 31), 2: date(yy, 6, 30),
                    3: date(yy, 9, 30), 4: date(yy, 12, 31)}[q]
            rl = (reg - qend).days
            ml = _MODEL_LAG[q]
            hol = ml - rl
            worst = min(worst, hol)
            print(f"{nemo:9} {qend.isoformat()} Q{q} {reg.isoformat()} "
                  f"{rl:5d} {ml:5d} {hol:5d}")
    print(f"\nHolgura minima global: {worst} d "
          f"({'HAY look-ahead' if worst < 0 else 'sin look-ahead'})")
