"""Verifica el rango histórico disponible para cada ticker en la BVL."""
import json
import requests

BASE = "https://dataondemand.bvl.com.pe"
TICKERS = ["SAGAC1", "CORAREC1", "ALICORC1", "CREDITC1", "BUENAVC1"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": "https://www.bvl.com.pe",
    "Referer": "https://www.bvl.com.pe/",
    "Accept": "application/json, text/plain, */*",
}


def get_sharevalues(ticker, start, end):
    r = requests.get(
        f"{BASE}/v1/stock-quote/share-values/{ticker}",
        params={"startDate": start, "endDate": end},
        headers=HEADERS, timeout=20,
    )
    if r.status_code != 200:
        return None, r.status_code
    data = r.json()
    values = data.get("values", [])
    return values, r.status_code


print("Rango completo 2005-2025\n")
for ticker in TICKERS:
    values, status = get_sharevalues(ticker, "2005-01-01", "2025-12-31")
    if values is None:
        print(f"  {ticker}: ERROR {status}")
        continue
    dates = [v[0] for v in values]
    prices = [float(v[1]) for v in values]
    print(f"  {ticker}: {len(values)} dias  min={min(dates)}  max={max(dates)}")
    print(f"    precio min={min(prices):.2f}  max={max(prices):.2f}  ultimo={prices[-1]:.2f}")
    # Muestra primeros y ultimos registros
    print(f"    primeros: {values[:3]}")
    print(f"    ultimos:  {values[-3:]}")
    print()
