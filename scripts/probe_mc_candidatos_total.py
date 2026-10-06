"""Cobertura mediatica (Media Cloud) de candidatos de reemplazo: TOTAL 2012-2025.

Una sola llamada story_count por ticker (rapido). Suficiente para juzgar
viabilidad de la parte de sentimiento. Los incumbentes (*) sirven de linea base.
"""
import datetime as dt
import os
import sys

import mediacloud.api as mc

TOKEN = os.environ.get("MEDIACLOUD_API_TOKEN", "")
if not TOKEN:
    raise SystemExit("Define MEDIACLOUD_API_TOKEN antes de ejecutar.")
PERU_NATIONAL = 34412158

QUERIES = {
    "INRETC1  (InRetail)":    '"InRetail" OR "Supermercados Peruanos" OR "Plaza Vea" OR "InkaFarma"',
    "CASAGRC1 (Casa Grande)": '("Casa Grande" AND (azucar OR azucarera OR agroindustrial OR Gloria OR ingenio OR cana))',
    "CPACASC1 (Pacasmayo)":   '"Cementos Pacasmayo" OR "Pacasmayo"',
    "AENZAC1  (Aenza)":       '"Aenza" OR "Graña y Montero" OR "Grana y Montero"',
    "LUSURC1  (Luz del Sur)": '"Luz del Sur"',
    "SAGAC1*  (Saga Fal.)":   '"Saga Falabella"',
    "CORAREC1*(A.Arequipa)":  '"Aceros Arequipa" OR "Corporacion Aceros Arequipa"',
    "ALICORC1*(Alicorp)":     '"Alicorp"',
    "CREDITC1*(BCP)":         '"Banco de Credito" OR "BCP" OR "Credicorp"',
    "BUENAVC1*(Buenavent.)":  '"Minas Buenaventura" OR "Compañia de Minas Buenaventura"',
}

START = dt.date(2012, 1, 1)
END = dt.date(2025, 12, 31)
WEEKS = round((END - START).days / 7)  # ~730 semanas

search = mc.SearchApi(TOKEN)
print(f"Collection = Peru Nacional  |  rango 2012-2025 ({WEEKS} semanas)  |  * = incumbente")
print(f"{'Ticker':<24} {'TOTAL':>8} {'/semana':>8}")
print("-" * 42)
for label, query in QUERIES.items():
    try:
        r = search.story_count(query, start_date=START, end_date=END,
                               collection_ids=[PERU_NATIONAL])
        n = r.get("relevant", 0) if isinstance(r, dict) else int(r)
        print(f"{label:<24} {n:>8} {n/WEEKS:>8.1f}", flush=True)
    except Exception as e:
        print(f"{label:<24} {'ERR':>8}  {e}", flush=True)
