"""Mide la LIQUIDEZ (proxy is_stale) de los candidatos de reemplazo de
SAGA/CORAREC y de varias alternativas de otros sectores, para la decision de
universo (ver docs/riesgos_transversales_datos.txt Tier1 #1 y R3).

Metrica: sobre el close diario oficial de la BVL (share-values) 2012-2025,
cuenta los dias en que el precio CAMBIO respecto al dia bursatil previo
(= "precios distintos"). % distinto alto = mas liquido / menos estancado.
    pct_distinct = dias_con_cambio / dias_con_precio
    pct_stale    = 1 - pct_distinct   (el precio se arrastro sin operar)
Incluye los 5 incumbentes como linea base ya aceptada.
"""
from __future__ import annotations
import requests

BASE = "https://dataondemand.bvl.com.pe/v1/stock-quote/share-values"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": "https://www.bvl.com.pe",
    "Referer": "https://www.bvl.com.pe/",
    "Accept": "application/json, text/plain, */*",
}
START, END = "2012-01-01", "2025-12-31"

# nemonico BVL -> (etiqueta, sector, rol)
CANDIDATOS = {
    # --- incumbentes (linea base) ---
    "SAGAC1":   ("Saga Falabella",   "Retail",        "incumbente*"),
    "CORAREC1": ("Aceros Arequipa",  "Manufactura",   "incumbente*"),
    "ALICORC1": ("Alicorp",          "Alimentos",     "incumbente*"),
    "CREDITC1": ("BCP",              "Banca",         "incumbente*"),
    "BUENAVC1": ("Buenaventura",     "Mineria",       "incumbente*"),
    # --- candidatos ya evaluados (jul-2026) ---
    "INRETC1":  ("InRetail",         "Retail",        "cand-retail"),
    "CASAGRC1": ("Casa Grande",      "Agro",          "cand-retail/agro"),
    "CPACASC1": ("Cem. Pacasmayo",   "Construccion",  "cand-construccion"),
    "AENZAC1":  ("Aenza",            "Construccion",  "cand-construccion"),
    "LUSURC1":  ("Luz del Sur",      "Utilities",     "cand-utilities"),
    # --- alternativas de otros sectores (exploracion) ---
    "FERREYC1": ("Ferreycorp",       "Bienes cap.",   "alt"),
    "UNACEMC1": ("UNACEM",           "Construccion",  "alt"),
    "ENGEPEC1": ("Engie Energia",    "Utilities",     "alt"),
    "MINSURI1": ("Minsur",           "Mineria",       "alt"),
    "VOLCABC1": ("Volcan",           "Mineria",       "alt"),
    "BACKUSI1": ("Backus",           "Bebidas",       "alt"),
    "CONTINC1": ("BBVA Continental",  "Banca",        "alt"),
    "SCOTIAC1": ("Scotiabank Peru",  "Banca",         "alt"),
    "NEXAPEC1": ("Nexa Resources",   "Mineria",       "alt"),
    "CORAREI1": ("Aceros Areq. Inv", "Manufactura",   "alt"),
    "GBVLAC1":  ("Grupo BVL",        "Financiero",    "alt"),
    "RELAPAC1": ("Refineria Pampilla","Energia",      "alt"),
}


def fetch_close(nemonico: str):
    try:
        r = requests.get(f"{BASE}/{nemonico}",
                         params={"startDate": START, "endDate": END},
                         headers=HEADERS, timeout=30)
        r.raise_for_status()
        vals = r.json().get("values", [])
    except Exception as e:
        return None, f"ERR {e}"
    # values = [[date, close], ...]; filtrar close>0
    rows = [(d, float(c)) for d, c in vals if c is not None and float(c) > 0]
    rows.sort(key=lambda x: x[0])
    return rows, None


print(f"Liquidez BVL {START}..{END}  (% distinto = dias con cambio de precio)")
hdr = (f"{'Nemonico':<10} {'Empresa':<18} {'Sector':<14} {'Rol':<18} "
       f"{'dias':>6} {'distintos':>9} {'%dist':>7} {'%stale':>7}  cobertura")
print(hdr)
print("-" * len(hdr))

resultados = []
for nem, (nombre, sector, rol) in CANDIDATOS.items():
    rows, err = fetch_close(nem)
    if err or not rows:
        print(f"{nem:<10} {nombre:<18} {sector:<14} {rol:<18} "
              f"{'--':>6}  {(err or 'sin datos')}")
        continue
    closes = [c for _, c in rows]
    dates = [d for d, _ in rows]
    n = len(closes)
    distintos = sum(1 for i in range(1, n) if closes[i] != closes[i - 1])
    pct_dist = distintos / n
    pct_stale = 1 - pct_dist
    cob = f"{dates[0][:10]}..{dates[-1][:10]}"
    print(f"{nem:<10} {nombre:<18} {sector:<14} {rol:<18} "
          f"{n:>6} {distintos:>9} {pct_dist:>6.1%} {pct_stale:>6.1%}  {cob}")
    resultados.append((nem, nombre, sector, rol, pct_dist))

# ranking por liquidez (solo candidatos/alternativas, no incumbentes)
print("\nRanking por liquidez (%dist, mas alto = mejor) - excl. incumbentes:")
for nem, nombre, sector, rol, pct in sorted(
        [r for r in resultados if not r[3].endswith("*")],
        key=lambda x: -x[4]):
    print(f"  {pct:>6.1%}  {nem:<10} {nombre:<18} ({sector})")
