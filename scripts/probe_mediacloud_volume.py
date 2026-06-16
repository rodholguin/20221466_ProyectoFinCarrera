"""Estima el volumen de noticias disponibles en Media Cloud para las 5 empresas.

Paso 1: descubre el collection_id de Perú Nacional.
Paso 2: cuenta noticias por ticker × año (story_count, sin paginar).
"""
import datetime as dt
import os

import mediacloud.api as mc

TOKEN = "4e0a7d22a81b303a1bf2239560ed63ea22324323"

QUERIES = {
    "CREDITC1": '"Banco de Credito" OR "BCP" OR "Credicorp"',
    "BUENAVC1": '"Buenaventura" OR "Minas Buenaventura"',
    "ALICORC1": '"Alicorp"',
    "SAGAC1":   '"Saga Falabella" OR "Falabella"',
    "CORAREC1": '"Aceros Arequipa" OR "Corporacion Aceros Arequipa"',
}

# ── Paso 1: Collection ID de Perú ────────────────────────────────────────────
print("=" * 60)
print("Buscando colecciones con 'Peru'...")
directory = mc.DirectoryApi(TOKEN)
results = directory.collection_list(name="Peru")
for c in results.get("results", []):
    print(f"  id={c['id']:>12}  {c['name']}")

# Intentar también con tilde
results2 = directory.collection_list(name="Perú")
for c in results2.get("results", []):
    if c not in results.get("results", []):
        print(f"  id={c['id']:>12}  {c['name']}  (con tilde)")

# ── Paso 2: Contar noticias por ticker × año ─────────────────────────────────
# Ajusta este ID con el que salga arriba (colección NACIONAL de Perú)
# Si hay varios, probar con el que diga "national" o "nacional"
COLLECTION_IDS_TO_TRY = [c["id"] for c in results.get("results", [])]
COLLECTION_IDS_TO_TRY += [c["id"] for c in results2.get("results", [])]
COLLECTION_IDS_TO_TRY = list(dict.fromkeys(COLLECTION_IDS_TO_TRY))  # dedup

if not COLLECTION_IDS_TO_TRY:
    print("\nNo se encontraron colecciones. Verifica el token.")
    exit(1)

print(f"\nIDs a probar: {COLLECTION_IDS_TO_TRY}")

search = mc.SearchApi(TOKEN)

YEARS = list(range(2012, 2026))

PERU_NATIONAL = 34412158  # confirmado arriba
for col_id in [PERU_NATIONAL]:
    print(f"\n{'='*60}")
    print(f"Collection ID = {col_id}")
    print(f"{'Ticker':<12} " + " ".join(f"{y}" for y in YEARS) + "  TOTAL")
    print("-" * (12 + len(YEARS) * 5 + 8))

    for ticker, query in QUERIES.items():
        counts = []
        total = 0
        for year in YEARS:
            try:
                result = search.story_count(
                    query,
                    start_date=dt.date(year, 1, 1),
                    end_date=dt.date(year, 12, 31),
                    collection_ids=[col_id],
                )
                # v5 devuelve dict {'relevant': N, 'total': M}
                n = result.get("relevant", 0) if isinstance(result, dict) else int(result)
                counts.append(n)
                total += n
            except Exception as e:
                counts.append(f"ERR:{e}")
        row = f"{ticker:<12} " + " ".join(
            f"{c:>5}" if isinstance(c, int) else f"{'ERR':>5}" for c in counts)
        print(f"{row}  {total:>7}")
