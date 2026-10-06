"""Valida los codigos de serie BCRP para los features macro (hasta inflacion):
confirma que cada codigo mapea a la variable correcta (nombre en 'config') y su
cobertura 2012-2025. Reusa el patron de src/market/fx.py (API abierto BCRP).

Macro decidido: cobre, TC (ya en fx.py), oro, tasa de referencia, EMBI, IPC.
"""
from __future__ import annotations
import requests

URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/json/{start}/{end}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
START, END = "2012-01-01", "2025-12-31"

CODES = {
    "PD04640PD": "TC USD/PEN venta bancario (control, ya en fx.py)",
    "PD04701XD": "Cobre Londres (cUS$/lb) diario",
    "PD04704XD": "Oro Londres (US$/oz troy) diario",
    "PD04709XD": "EMBIG Peru spread (pbs) diario",
    "PD04722MM": "Tasa de referencia politica monetaria (%) mensual",
    "PN01271PM": "IPC Lima Metropolitana mensual",
}


def fetch(code: str):
    for start, end in [(START, END), (START[:7], END[:7]), (START[:4], END[:4])]:
        try:
            r = requests.get(URL.format(code=code, start=start, end=end),
                             headers=HEADERS, timeout=90)
            if r.status_code >= 400:
                continue
            j = r.json()
            if j.get("periods"):
                return j
        except Exception as e:
            last = str(e)
    return None


for code, desc in CODES.items():
    print(f"\n=== {code}  ({desc}) ===")
    j = fetch(code)
    if not j:
        print("  ERROR: sin respuesta valida")
        continue
    # nombre reportado por el API
    names = [s.get("name") for s in j.get("config", {}).get("series", [])]
    periods = j["periods"]
    vals = []
    for it in periods:
        v = it["values"][0]
        if v not in ("n.d.", "", None):
            try:
                vals.append(float(v))
            except ValueError:
                pass
    print(f"  API name : {names}")
    print(f"  periodos : {len(periods)}  (con dato: {len(vals)})")
    if periods:
        print(f"  rango    : {periods[0]['name']}  ..  {periods[-1]['name']}")
    if vals:
        print(f"  valores  : min={min(vals):.2f}  max={max(vals):.2f}  "
              f"ult={vals[-1]:.2f}")
