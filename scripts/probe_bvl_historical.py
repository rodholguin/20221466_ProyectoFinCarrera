"""Prueba endpoints históricos de la BVL y grep del bundle para parámetros."""
import json
import re
import requests

BASE = "https://dataondemand.bvl.com.pe"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": "https://www.bvl.com.pe",
    "Referer": "https://www.bvl.com.pe/emisores/SAGAC1",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
}


def req(method, path, params=None, body=None, label=""):
    url = BASE + path
    try:
        if method == "POST":
            r = requests.post(url, json=body, params=params, headers=HEADERS, timeout=15)
        else:
            r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        try:
            body_str = json.dumps(r.json(), ensure_ascii=False)[:700]
        except Exception:
            body_str = r.text[:400].replace("\n", " ")
        tag = label or ""
        print(f"  {r.status_code}  {method} {r.url}  {tag}")
        if r.status_code < 400:
            print(f"    {body_str}")
        print()
        return r
    except Exception as e:
        print(f"  ERR  {method} {url}  {e}\n")


# ── 1. quotationHistory: /v1/issuers/stock ───────────────────────────────────
print("=" * 60)
print("1. quotationHistory = /v1/issuers/stock")
req("GET",  "/v1/issuers/stock", {"nemonico": "SAGAC1"})
req("GET",  "/v1/issuers/stock", {"nemonico": "SAGAC1", "from": "2024-01-01", "to": "2024-03-31"})
req("POST", "/v1/issuers/stock", body={"nemonico": "SAGAC1"})
req("POST", "/v1/issuers/stock", body={"nemonico": "SAGAC1", "from": "2024-01-01", "to": "2024-03-31"})

# ── 2. Endpoints que devolvieron 405 (probar POST) ───────────────────────────
print("=" * 60)
print("2. Endpoints 405 -> probando POST")
for path, body in [
    ("/v1/stock-quote/market",  {"nemonico": "SAGAC1"}),
    ("/v1/stock-quote/home",    {"nemonico": "SAGAC1"}),
    ("/v1/stock-quote/top",     None),
    ("/v1/index-historical-data", {"index": "IGBVL", "from": "2024-01-01", "to": "2024-03-31"}),
]:
    req("POST", path, body=body)

# ── 3. share-values con ticker en path ──────────────────────────────────────
print("=" * 60)
print("3. /v1/stock-quote/share-values/{nemonico}")
for ticker in ["SAGAC1", "CORAREC1", "ALICORC1"]:
    for params in [
        None,
        {"from": "2024-01-01", "to": "2024-03-31"},
        {"fechaDesde": "2024-01-01", "fechaHasta": "2024-03-31"},
        {"startDate": "2024-01-01", "endDate": "2024-03-31"},
    ]:
        req("GET", f"/v1/stock-quote/share-values/{ticker}", params=params)

# ── 4. Grep bundle para parámetros de quotationHistory / issuers/stock ──────
print("=" * 60)
print("4. GREP bundle: parámetros de issuers/stock y share-values")
print("   Descargando main.js...")
r = requests.get("https://www.bvl.com.pe/main.1ca3dd889220439bbef2.js",
                 headers={**HEADERS, "Accept": "*/*"}, timeout=30)
js = r.text

for kw in ["issuers/stock", "quotationHistory", "share-values", "share-value",
           "getQuotation", "getHistory", "getShareValues", "fechaDesde",
           "startDate", "endDate", "dateFrom", "dateTo"]:
    positions = [m.start() for m in re.finditer(re.escape(kw), js)]
    if positions:
        print(f"\n  keyword='{kw}'  ({len(positions)} ocurrencias)")
        for pos in positions[:4]:
            ctx = js[max(0, pos - 150):pos + 300]
            print(f"    ...{ctx}...")
