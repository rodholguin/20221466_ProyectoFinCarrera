"""Opción B: Capital Emitido del SMV + Opción C: BVL share endpoint."""
import sys, json
sys.path.insert(0, ".")
from pathlib import Path
import requests

UNIVERSE = [
    {"bvl": "CREDITC1", "rpj": "B80005"},
    {"bvl": "BUENAVC1", "rpj": "B20003"},
    {"bvl": "ALICORC1", "rpj": "B30006"},
    {"bvl": "SAGAC1",   "rpj": "014313"},
    {"bvl": "CORAREC1", "rpj": "CI0003"},
]
SEP = "=" * 65
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": "https://www.bvl.com.pe",
    "Referer": "https://www.bvl.com.pe/",
    "Accept": "application/json",
}

# ── OPCIÓN B: Capital Emitido del SMV ─────────────────────────────────────
print(SEP)
print("OPCION B: Capital Emitido (1D0701) del BalanceGeneral SMV Q4-2023")
print(SEP)
cache_dir = Path("data/raw/smv_cache")
bg_file = cache_dir / "obtener_BalanceGeneral_2023Q4_I.json"
data = json.loads(bg_file.read_text())

CAPITAL_ACCOUNTS = ["1D0701", "1D0703", "1D0711", "1D07ST"]
BANKING_ACCOUNTS = ["1B0701", "1B0703", "1B0711", "1B07ST",
                    "2B0701", "2B07ST"]  # taxonomía SBS

for a in UNIVERSE:
    rows = [r for r in data if r.get("RPJ") == a["rpj"]]
    moneda = rows[0].get("Moneda", "?") if rows else "?"
    print(f"\n  {a['bvl']} ({a['rpj']}) — Moneda: {moneda}")
    found_any = False
    for cta in CAPITAL_ACCOUNTS + BANKING_ACCOUNTS:
        r = next((x for x in rows if x.get("Cuenta") == cta), None)
        if r and r.get("Monto1") is not None:
            m = r["Monto1"]
            desc = r.get("DescripcionCuenta", "")
            print(f"    {cta}: {desc:50} = {m:>15,} miles")
            found_any = True
    if not found_any:
        # Mostrar todos los grupos de cuentas disponibles
        grupos = sorted(set(r.get("Cuenta","")[:4] for r in rows))
        print(f"    [No se encontraron cuentas de capital. Grupos: {grupos}]")
        # Mostrar cuentas que contengan "capital" en la descripción
        for r in rows:
            if "capital" in r.get("DescripcionCuenta","").lower():
                print(f"    >> {r['Cuenta']}: {r['DescripcionCuenta']} = {r.get('Monto1')}")

# ── OPCIÓN C: BVL share + share-values endpoint ───────────────────────────
print()
print(SEP)
print("OPCION C: BVL endpoints de emisores (buscando shares info)")
print(SEP)
for a in UNIVERSE[:2]:  # Solo 2 para no sobrecargar
    for path, params in [
        ("/v1/stock-quote/share",        {"nemonico": a["bvl"]}),
        ("/v1/issuers/stock",            {"nemonico": a["bvl"]}),
        ("/v1/stock-quote/home",         {"nemonico": a["bvl"]}),
    ]:
        try:
            r = requests.get("https://dataondemand.bvl.com.pe" + path,
                             params=params, headers=HEADERS, timeout=10)
            body = r.json() if "json" in r.headers.get("content-type","") else r.text[:200]
            print(f"  {a['bvl']} {path}: {r.status_code}  {str(body)[:400]}")
        except Exception as e:
            print(f"  ERROR: {e}")
