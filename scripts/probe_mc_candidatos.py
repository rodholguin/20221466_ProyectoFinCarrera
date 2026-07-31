"""Estima cobertura mediática (Media Cloud) de los CANDIDATOS de reemplazo de
SAGA/CORAREC, para evaluar si son viables para la parte de sentimiento (R5).

Cuenta noticias por ticker x año (story_count, sin paginar) en la coleccion
Peru Nacional. Incluye SAGA y CORAREC como linea base de comparacion, y los
otros 3 incumbentes como referencia del piso de cobertura ya aceptado.
"""
import datetime as dt
import os

import mediacloud.api as mc

TOKEN = os.environ.get("MEDIACLOUD_API_TOKEN", "")
if not TOKEN:
    raise SystemExit("Define MEDIACLOUD_API_TOKEN antes de ejecutar.")
PERU_NATIONAL = 34412158

# Queries con anclaje. Los nombres ambiguos (Casa Grande, Aenza) se acotan.
QUERIES = {
    # --- CANDIDATOS ---
    "INRETC1  (InRetail)":   '"InRetail" OR "Supermercados Peruanos" OR "Plaza Vea" OR "InkaFarma"',
    "CASAGRC1 (Casa Grande)":'("Casa Grande" AND (azucar OR azucarera OR agroindustrial OR Gloria OR ingenio OR cana))',
    "CPACASC1 (Pacasmayo)":  '"Cementos Pacasmayo" OR "Pacasmayo"',
    "AENZAC1  (Aenza)":      '"Aenza" OR "Graña y Montero" OR "Grana y Montero"',
    "LUSURC1  (Luz del Sur)":'"Luz del Sur"',
    # --- INCUMBENTES (linea base) ---
    "SAGAC1*  (Saga Fal.)":  '"Saga Falabella"',
    "CORAREC1*(A.Arequipa)": '"Aceros Arequipa" OR "Corporacion Aceros Arequipa"',
    "ALICORC1*(Alicorp)":    '"Alicorp"',
    "CREDITC1*(BCP)":        '"Banco de Credito" OR "BCP" OR "Credicorp"',
    "BUENAVC1*(Buenavent.)": '"Minas Buenaventura" OR "Compañia de Minas Buenaventura"',
}

YEARS = list(range(2012, 2026))
search = mc.SearchApi(TOKEN)

print(f"Collection = Peru Nacional ({PERU_NATIONAL})   * = incumbente")
hdr = f"{'Ticker':<24} " + " ".join(f"{y%100:>4}" for y in YEARS) + f"  {'TOTAL':>7}  {'>=1/sem':>7}"
print(hdr)
print("-" * len(hdr))

for label, query in QUERIES.items():
    counts, total = [], 0
    for year in YEARS:
        try:
            r = search.story_count(query,
                                   start_date=dt.date(year, 1, 1),
                                   end_date=dt.date(year, 12, 31),
                                   collection_ids=[PERU_NATIONAL])
            n = r.get("relevant", 0) if isinstance(r, dict) else int(r)
        except Exception as e:
            n = -1
            print(f"  ERR {label} {year}: {e}")
        counts.append(n)
        if n > 0:
            total += n
    # semanas con >=1 nota (aprox): total/52 promedio anual como referencia gruesa
    weekly = total / (len(YEARS) * 52)
    row = f"{label:<24} " + " ".join(f"{c:>4}" if c >= 0 else f"{'ERR':>4}" for c in counts)
    print(f"{row}  {total:>7}  {weekly:>6.1f}")
