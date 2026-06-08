"""Exploración del API de la BVL — ejecutar una vez para descubrir endpoints."""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
    "Referer": "https://www.bvl.com.pe/",
}
HEADERS_JSON = {**HEADERS, "Accept": "application/json, text/plain, */*"}

TICKERS = ["SAGAC1", "CORAREC1", "ALICORC1", "CREDITC1", "BUENAVC1"]


# ── 1. Obtener HTML principal para encontrar bundles JS ──────────────────────
def find_js_bundles():
    print("=" * 60)
    print("1. BUSCANDO BUNDLES JS EN www.bvl.com.pe")
    for url in ["https://www.bvl.com.pe", "https://www.bvl.com.pe/mercado/resumen-mercado"]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            html = r.text
            print(f"\n  {url}  status={r.status_code}  len={len(html)}")
            scripts = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', html)
            for s in scripts[:20]:
                print(f"    script: {s}")
            api_refs = re.findall(r'((?:https?:)?//[^\s"\'<>]+(?:api|v\d|data|quotes|prices|market)[^\s"\'<>]*)', html)
            for a in set(api_refs):
                print(f"    api-ref: {a}")
        except Exception as e:
            print(f"  ERR: {e}")


# ── 2. Probar familia de endpoints dataondemand ──────────────────────────────
def probe_dataondemand():
    print("\n" + "=" * 60)
    print("2. PROBANDO ENDPOINTS DATAONDEMAND")
    base = "https://dataondemand.bvl.com.pe"
    paths = [
        "/",
        "/v1/",
        "/v2/",
        "/v1/quotes/",
        "/v1/marketdata/",
        "/v1/prices/",
        "/v1/history/",
        "/v1/stocks/",
        "/v1/securities/",
        "/v1/instruments/",
        "/v1/timeseries/",
        "/v1/eod/",          # end-of-day pattern común
        "/v1/cotizaciones/",
        "/v1/precios/",
    ]
    for path in paths:
        try:
            r = requests.get(base + path, headers=HEADERS_JSON, timeout=10)
            body_preview = r.text[:200].replace("\n", " ")
            print(f"  {r.status_code}  {path}  [{r.headers.get('content-type','')[:40]}]  {body_preview}")
        except Exception as e:
            print(f"  ERR  {path}  {e}")


# ── 3. Probar endpoints con ticker específico ────────────────────────────────
def probe_ticker_endpoints():
    print("\n" + "=" * 60)
    print("3. PROBANDO ENDPOINTS CON TICKER (SAGAC1)")
    ticker = "SAGAC1"
    candidates = [
        f"https://dataondemand.bvl.com.pe/v1/quotes/{ticker}",
        f"https://dataondemand.bvl.com.pe/v1/quotes/?symbol={ticker}",
        f"https://dataondemand.bvl.com.pe/v1/marketdata/{ticker}",
        f"https://dataondemand.bvl.com.pe/v1/history/{ticker}",
        f"https://dataondemand.bvl.com.pe/v1/timeseries/{ticker}",
        f"https://www.bvl.com.pe/api/quotes/{ticker}",
        f"https://www.bvl.com.pe/api/v1/quotes/{ticker}",
        f"https://www.bvl.com.pe/api/market/{ticker}",
        # Patrón antiguo del sitio BVL
        f"http://www.bvl.com.pe/inf_cotizaciones_{ticker}.html",
    ]
    for url in candidates:
        try:
            r = requests.get(url, headers=HEADERS_JSON, timeout=10)
            body_preview = r.text[:300].replace("\n", " ")
            print(f"  {r.status_code}  {url}")
            if r.status_code < 400:
                print(f"    BODY: {body_preview}")
        except Exception as e:
            print(f"  ERR  {url}  {e}")


# ── 4. Intentar obtener los archivos JS del SPA para grep de endpoints ───────
def grep_js_bundles():
    print("\n" + "=" * 60)
    print("4. DESCARGANDO BUNDLES JS DEL SPA BVL")
    # El SPA de la BVL suele usar Nuxt/Vue; los chunks estarán en /_nuxt/ o /js/
    js_candidates = [
        "https://www.bvl.com.pe/_nuxt/",
        "https://www.bvl.com.pe/static/js/",
        "https://www.bvl.com.pe/js/",
    ]
    for url in js_candidates:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            print(f"  {r.status_code}  {url}")
        except Exception as e:
            print(f"  ERR  {url}  {e}")

    # Intentar cargar la página de un valor específico y extraer scripts
    print("\n  Cargando ficha de valor SAGAC1...")
    for url in [
        "https://www.bvl.com.pe/emisores/SAGAC1",
        "https://www.bvl.com.pe/mercado/valores/SAGAC1",
        "https://www.bvl.com.pe/emisores/acciones-inscritas/SAGAC1",
    ]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            html = r.text
            print(f"\n  {r.status_code}  {url}  len={len(html)}")
            scripts = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', html)
            for s in scripts[:10]:
                full = s if s.startswith("http") else "https://www.bvl.com.pe" + s
                print(f"    script: {full}")
                # Intentar descargar y grep el bundle
                try:
                    js = requests.get(full, headers=HEADERS, timeout=15).text
                    endpoints = re.findall(r'["\x60](/(?:api|v\d)[^"^x60\s]{5,60})["\x60]', js)
                    if endpoints:
                        print(f"      endpoints en JS: {list(set(endpoints))[:15]}")
                except Exception:
                    pass
        except Exception as e:
            print(f"  ERR  {url}  {e}")


if __name__ == "__main__":
    find_js_bundles()
    probe_dataondemand()
    probe_ticker_endpoints()
    grep_js_bundles()
