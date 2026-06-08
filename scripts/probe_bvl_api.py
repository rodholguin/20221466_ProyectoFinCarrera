"""Prueba los endpoints reales de api.bvl.com.pe descubiertos en los bundles."""
import json
import re
import requests

API_BASE = "https://api.bvl.com.pe"
TICKERS = ["SAGAC1", "CORAREC1", "ALICORC1", "CREDITC1", "BUENAVC1"]

HEADERS_BASE = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": "https://www.bvl.com.pe",
    "Referer": "https://www.bvl.com.pe/",
    "Accept-Language": "es-PE,es;q=0.9",
}
HEADERS_JSON = {**HEADERS_BASE, "Accept": "application/json, text/plain, */*"}


def try_endpoint(path, params=None, method="GET", extra_headers=None):
    url = API_BASE + path
    h = {**HEADERS_JSON, **(extra_headers or {})}
    try:
        if method == "POST":
            r = requests.post(url, json=params, headers=h, timeout=15)
        else:
            r = requests.get(url, params=params, headers=h, timeout=15)
        ct = r.headers.get("content-type", "")
        body = r.text[:600].replace("\n", " ")
        print(f"  {r.status_code}  {method} {url}  params={params}")
        print(f"    ct={ct}  body={body}")
        if r.status_code == 200 and "json" in ct:
            return r.json()
    except Exception as e:
        print(f"  ERR  {url}  {e}")
    return None


# ── 1. Probar stock-quote endpoints ─────────────────────────────────────────
print("=" * 60)
print("1. PROBANDO /v1/stock-quote/* (descubiertos en main.js)")
ticker = "SAGAC1"

paths = [
    ("/v1/stock-quote/daily", {"nemonico": ticker}),
    ("/v1/stock-quote/daily", {"ticker": ticker}),
    ("/v1/stock-quote/daily", {"symbol": ticker}),
    ("/v1/stock-quote/daily", {"code": ticker, "from": "2024-01-01", "to": "2024-03-01"}),
    ("/v1/stock-quote/market", None),
    ("/v1/stock-quote/market", {"nemonico": ticker}),
    ("/v1/stock-quote/home", None),
    ("/v1/stock-quote/share", {"nemonico": ticker}),
    ("/v1/stock-quote/share-value", {"nemonico": ticker}),
]
for path, params in paths:
    try_endpoint(path, params)

# ── 2. Probar otros endpoints de mercado ────────────────────────────────────
print("\n" + "=" * 60)
print("2. OTROS ENDPOINTS DE MERCADO")

other = [
    ("/v1/market-summary", None),
    ("/v1/reference-prices", {"nemonico": ticker}),
    ("/v1/reference-prices", None),
    ("/v1/issuers", None),
    ("/v1/issuers/stock", None),
    ("/v1/index-historical-data", None),
    ("/v1/index-historical-data", {"index": "IGBVL", "from": "2024-01-01", "to": "2024-03-01"}),
    ("/v1/indices", None),
    ("/v1/corporate-actions", {"nemonico": ticker}),
]
for path, params in other:
    try_endpoint(path, params)

# ── 3. Grep del main bundle para contexto de stock-quote/daily ──────────────
print("\n" + "=" * 60)
print("3. CONTEXTO DE stock-quote EN EL BUNDLE MAIN.JS")

main_url = "https://www.bvl.com.pe/main.1ca3dd889220439bbef2.js"
print(f"  Descargando {main_url}...")
try:
    r = requests.get(main_url, headers=HEADERS_BASE, timeout=30)
    js = r.text
    print(f"  Descargado: {len(js)//1024}KB")

    # Extraer contexto alrededor de stock-quote
    for keyword in ["stock-quote", "stock_quote", "stockquote", "nemonico", "fechaDesde", "startDate"]:
        positions = [m.start() for m in re.finditer(re.escape(keyword), js)]
        if positions:
            print(f"\n  keyword='{keyword}'  ocurrencias={len(positions)}")
            for pos in positions[:5]:
                ctx = js[max(0, pos-120):pos+200]
                print(f"    ...{ctx}...")

    # Buscar el base URL de la API
    api_base_refs = re.findall(r'["\`](https?://api\.bvl\.com\.pe[^"\`\s]{0,80})["\`]', js)
    print(f"\n  Base URLs de api.bvl.com.pe: {list(set(api_base_refs))[:20]}")

    # Buscar token/auth patterns
    auth_refs = re.findall(r'["\`]((?:Authorization|Bearer|token|apiKey|x-api-key)[^"\`\s]{0,80})["\`]', js, re.I)
    print(f"\n  Auth patterns: {list(set(auth_refs))[:15]}")

except Exception as e:
    print(f"  ERR: {e}")
