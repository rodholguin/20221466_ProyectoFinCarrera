"""MediaCloud: cobertura mediatica de FERREYCORP y MINSUR (candidatos nuevos),
con SAGA/CORAREC/BUENAVENTURA como linea base. Coleccion Peru Nacional."""
import datetime as dt
import os
import mediacloud.api as mc

TOKEN = os.environ.get("MEDIACLOUD_API_TOKEN", "")
if not TOKEN:
    raise SystemExit("Define MEDIACLOUD_API_TOKEN antes de ejecutar.")
PERU_NATIONAL = 34412158

QUERIES = {
    "FERREYC1 (Ferreycorp)": '"Ferreycorp" OR "Ferreyros"',
    "MINSURI1 (Minsur)":     '"Minsur"',
    # linea base
    "SAGAC1*  (Saga Fal.)":  '"Saga Falabella"',
    "CORAREC1*(A.Arequipa)": '"Aceros Arequipa" OR "Corporacion Aceros Arequipa"',
    "BUENAVC1*(Buenavent.)": '"Minas Buenaventura" OR "Compañia de Minas Buenaventura"',
}
YEARS = list(range(2012, 2026))
search = mc.SearchApi(TOKEN)

print(f"Collection = Peru Nacional ({PERU_NATIONAL})   * = incumbente")
hdr = f"{'Ticker':<24} " + " ".join(f"{y%100:>4}" for y in YEARS) + f"  {'TOTAL':>7}  {'/sem':>5}"
print(hdr)
print("-" * len(hdr))
for label, query in QUERIES.items():
    counts, total = [], 0
    for year in YEARS:
        try:
            r = search.story_count(query, start_date=dt.date(year, 1, 1),
                                   end_date=dt.date(year, 12, 31),
                                   collection_ids=[PERU_NATIONAL])
            n = r.get("relevant", 0) if isinstance(r, dict) else int(r)
        except Exception as e:
            n = -1
            print(f"  ERR {label} {year}: {e}")
        counts.append(n)
        if n > 0:
            total += n
    weekly = total / (len(YEARS) * 52)
    row = f"{label:<24} " + " ".join(f"{c:>4}" if c >= 0 else f"{'ERR':>4}" for c in counts)
    print(f"{row}  {total:>7}  {weekly:>5.1f}")
