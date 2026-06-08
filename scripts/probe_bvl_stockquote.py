"""Prueba el endpoint real descubierto: dataondemand.bvl.com.pe/v1/stock-quote/daily."""
import json
import requests

BASE = "https://dataondemand.bvl.com.pe"
TICKERS = ["SAGAC1", "CORAREC1", "ALICORC1", "CREDITC1", "BUENAVC1"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": "https://www.bvl.com.pe",
    "Referer": "https://www.bvl.com.pe/emisores/SAGAC1",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-PE,es;q=0.9",
}


def get(path, params=None):
    url = BASE + path
    r = requests.get(url, params=params, headers=HEADERS, timeout=15)
    ct = r.headers.get("content-type", "")
    try:
        body = r.json()
        body_str = json.dumps(body, ensure_ascii=False)[:600]
    except Exception:
        body_str = r.text[:400].replace("\n", " ")
    print(f"  {r.status_code}  {r.url}")
    print(f"    ct={ct}")
    print(f"    body={body_str}")
    print()
    return r


# ── 1. Endpoint principal de gráfico histórico ──────────────────────────────
print("=" * 60)
print("1. /v1/stock-quote/daily  (graph endpoint)")
for ticker in TICKERS:
    print(f"\n  --- {ticker} ---")
    get("/v1/stock-quote/daily", {"nemonico": ticker, "today": "2025-01-31"})

# ── 2. Variantes del parámetro de fecha ─────────────────────────────────────
print("=" * 60)
print("2. Variantes de parámetros para SAGAC1")
for params in [
    {"nemonico": "SAGAC1"},
    {"nemonico": "SAGAC1", "today": "2025-01-01"},
    {"nemonico": "SAGAC1", "date": "2025-01-01"},
    {"nemonico": "SAGAC1", "startDate": "2005-01-01", "endDate": "2025-01-01"},
    {"nemonico": "SAGAC1", "from": "2005-01-01", "to": "2025-01-01"},
    {"nemonico": "SAGAC1", "fechaDesde": "2005-01-01", "fechaHasta": "2025-01-01"},
]:
    get("/v1/stock-quote/daily", params)

# ── 3. Otros endpoints del mismo dominio ────────────────────────────────────
print("=" * 60)
print("3. Otros endpoints dataondemand")
for path, params in [
    ("/v1/stock-quote/share",       {"nemonico": "SAGAC1"}),
    ("/v1/stock-quote/share-values/SAGAC1", None),
    ("/v1/stock-quote/market",      None),
    ("/v1/stock-quote/home",        None),
    ("/v1/stock-quote/top",         None),
    ("/v1/index-historical-data",   {"index": "IGBVL"}),
    ("/v1/indices",                 None),
    ("/v1/issuers",                 None),
    ("/v1/issuers/stock",           None),
    ("/v1/financial-statements/",   {"nemonico": "SAGAC1"}),
    ("/v1/reference-prices",        {"nemonico": "SAGAC1"}),
    ("/v1/market-summary",          None),
]:
    get(path, params)
