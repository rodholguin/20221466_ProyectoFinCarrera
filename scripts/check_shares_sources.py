"""Evalúa las 3 fuentes posibles para obtener número de acciones.

Opción A: yfinance .info (sharesOutstanding)
Opción B: Capital Emitido SMV / valor nominal (par value) por empresa
Opción C: BVL dataondemand endpoints de emisores (ya conocemos share-values)
"""
import sys, json
sys.path.insert(0, ".")
from pathlib import Path

UNIVERSE = [
    {"bvl": "CREDITC1", "yahoo": "CREDITC1.LM", "rpj": "B80005"},
    {"bvl": "BUENAVC1", "yahoo": "BVN",          "rpj": "B20003"},
    {"bvl": "ALICORC1", "yahoo": "ALICORC1.LM", "rpj": "B30006"},
    {"bvl": "SAGAC1",   "yahoo": "SAGAC1.LM",   "rpj": "014313"},
    {"bvl": "CORAREC1", "yahoo": "CORAREC1.LM", "rpj": "CI0003"},
]

SEP = "=" * 65

# ─── OPCIÓN A: yfinance sharesOutstanding ───────────────────────────────────
print(SEP)
print("OPCION A: yfinance .info['sharesOutstanding']")
print(SEP)
try:
    import yfinance as yf
    for a in UNIVERSE:
        try:
            info = yf.Ticker(a["yahoo"]).info
            shares = info.get("sharesOutstanding")
            mktcap = info.get("marketCap")
            price  = info.get("currentPrice") or info.get("regularMarketPrice")
            print(f"  {a['bvl']:10} ({a['yahoo']:14}) "
                  f"sharesOutstanding={shares}  marketCap={mktcap}  price={price}")
        except Exception as e:
            print(f"  {a['bvl']:10}: ERROR {e}")
except ImportError:
    print("  yfinance no disponible")

# ─── OPCIÓN B: Capital Emitido del SMV ─────────────────────────────────────
print()
print(SEP)
print("OPCION B: Capital Emitido (cuenta 1D0701) del BalanceGeneral SMV")
print(SEP)
cache_dir = Path("data/raw/smv_cache")
bg_file = cache_dir / "obtener_BalanceGeneral_2023Q4_I.json"
if bg_file.exists():
    data = json.loads(bg_file.read_text())
    print(f"  (Datos: Q4-2023, en miles de soles o USD)\n")
    for a in UNIVERSE:
        rows = [r for r in data if r.get("RPJ") == a["rpj"]]
        capital_row = next((r for r in rows if r.get("Cuenta") == "1D0701"), None)
        acciones_inv = next((r for r in rows if r.get("Cuenta") == "1D0703"), None)
        treasury     = next((r for r in rows if r.get("Cuenta") == "1D0711"), None)
        moneda_row   = rows[0].get("Moneda", "?") if rows else "?"
        cap = capital_row["Monto1"] if capital_row else None
        inv = acciones_inv["Monto1"] if acciones_inv else 0
        tre = treasury["Monto1"] if treasury else 0
        print(f"  {a['bvl']:10}  Capital Emitido={cap:>15,} miles {moneda_row}")
        print(f"             Acciones Inversión={inv:>15,}  Acc.Propias={tre:>12,}")
        if cap:
            # Si par value fuera 1.00, shares = cap*1000 / 1.00
            print(f"             → Si par=1.00: {cap*1000:,} acciones")
            print(f"             → Si par=0.10: {cap*1000/0.10:,.0f} acciones")
        print()
else:
    print(f"  Cache no encontrado: {bg_file}")

# ─── OPCIÓN C: BVL stock-quote/share endpoint ───────────────────────────────
print(SEP)
print("OPCION C: BVL dataondemand /v1/stock-quote/share (ya conocido)")
print(SEP)
import requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": "https://www.bvl.com.pe",
    "Referer": "https://www.bvl.com.pe/",
    "Accept": "application/json",
}
for a in UNIVERSE:
    try:
        r = requests.get(
            f"https://dataondemand.bvl.com.pe/v1/stock-quote/share",
            params={"nemonico": a["bvl"]},
            headers=HEADERS, timeout=10
        )
        body = r.json() if r.headers.get("content-type","").startswith("application/json") else r.text[:200]
        print(f"  {a['bvl']:10}  status={r.status_code}  body={str(body)[:300]}")
    except Exception as e:
        print(f"  {a['bvl']:10}  ERROR: {e}")
