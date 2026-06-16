"""Diagnóstico Media Cloud: verifica que story_count funciona y prueba queries."""
import datetime as dt
import mediacloud.api as mc

TOKEN = "4e0a7d22a81b303a1bf2239560ed63ea22324323"
PERU_NATIONAL = 34412158

search = mc.SearchApi(TOKEN)

# 1. Query broad para verificar que la colección tiene datos
print("=== Test 1: query amplia 'Peru' ===")
for q in ["Peru", "Lima", "economía", "bolsa"]:
    result = search.story_count(
        q,
        start_date=dt.date(2023, 1, 1),
        end_date=dt.date(2023, 12, 31),
        collection_ids=[PERU_NATIONAL],
    )
    print(f"  query={q!r:20}  resultado raw = {result!r}")

print()

# 2. Queries de las empresas con variantes
print("=== Test 2: queries de empresas (2020-2023) ===")
queries = [
    ("Alicorp simple",      "Alicorp"),
    ("Alicorp quoted",      '"Alicorp"'),
    ("BCP simple",          "BCP"),
    ("Banco Credito",       '"Banco de Credito"'),
    ("Falabella simple",    "Falabella"),
    ("Buenaventura simple", "Buenaventura"),
    ("Aceros Arequipa",     '"Aceros Arequipa"'),
]
for label, q in queries:
    result = search.story_count(
        q,
        start_date=dt.date(2020, 1, 1),
        end_date=dt.date(2023, 12, 31),
        collection_ids=[PERU_NATIONAL],
    )
    print(f"  {label:<25}  raw = {result!r}")

print()

# 3. Mostrar tipo y atributos del objeto retornado
print("=== Test 3: tipo del objeto retornado ===")
result = search.story_count(
    "Alicorp",
    start_date=dt.date(2022, 1, 1),
    end_date=dt.date(2022, 12, 31),
    collection_ids=[PERU_NATIONAL],
)
print(f"  type: {type(result)}")
print(f"  repr: {result!r}")
if hasattr(result, "__dict__"):
    print(f"  __dict__: {result.__dict__}")
if hasattr(result, "_asdict"):
    print(f"  _asdict: {result._asdict()}")
