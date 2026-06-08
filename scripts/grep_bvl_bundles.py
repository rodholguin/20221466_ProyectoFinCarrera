"""Descarga los bundles JS del sitio BVL y extrae endpoints de API."""
import re
import requests

BASE = "https://www.bvl.com.pe"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Accept": "*/*",
    "Referer": BASE,
}

# Patrones para detectar endpoints de API en JavaScript minificado
ENDPOINT_RE = re.compile(
    r'["`\']'
    r'(/(?:api|v\d|services|market|emisores|cotizaciones|precios|acciones)'
    r'[^"`\'\s<>{}\[\]]{3,120})'
    r'["`\']'
)
URL_RE = re.compile(
    r'["`\']'
    r'(https?://[^\s"`\'\[\]{}]{10,120}(?:api|v\d|data|quotes|price|market)[^\s"`\'\[\]{}]*)'
    r'["`\']'
)
DOMAIN_RE = re.compile(r'["`\']([a-z0-9-]+\.bvl\.com\.pe(?:/[^\s"`\'<>{}]{0,80})?)["`\']')


def fetch(url, timeout=20):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


def grep_bundle(name, js_text):
    endpoints = set(ENDPOINT_RE.findall(js_text))
    urls = set(URL_RE.findall(js_text))
    domains = set(DOMAIN_RE.findall(js_text))
    if endpoints or urls or domains:
        print(f"\n  [{name}]  ({len(js_text)//1024}KB)")
        for e in sorted(endpoints)[:30]:
            print(f"    PATH  {e}")
        for u in sorted(urls)[:20]:
            print(f"    URL   {u}")
        for d in sorted(domains)[:20]:
            print(f"    DOM   {d}")


# ── Paso 1: obtener todos los scripts del HTML ──────────────────────────────
print("Descargando HTML de la ficha SAGAC1...")
status, html = fetch(f"{BASE}/emisores/SAGAC1")
print(f"  status={status}  len={len(html)}")

all_scripts = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', html)
full_scripts = []
for s in all_scripts:
    full = s if s.startswith("http") else BASE + "/" + s.lstrip("/")
    full_scripts.append(full)

print(f"\nScripts encontrados: {len(full_scripts)}")

# ── Paso 2: grep en línea dentro del HTML ──────────────────────────────────
print("\n--- GREP en HTML inline ---")
grep_bundle("HTML-inline", html)

# También buscar JSON embebido con datos de configuración
json_configs = re.findall(r'window\.__[A-Z_]+\s*=\s*(\{[^;]{10,500})', html)
for j in json_configs[:5]:
    print(f"  config: {j[:300]}")

# ── Paso 3: descargar y grep cada bundle ───────────────────────────────────
print("\n--- GREP en bundles JS ---")
priority_keywords = ["elements", "main", "app", "bvl", "market", "emisor", "api"]
priority_scripts = sorted(
    full_scripts,
    key=lambda s: -any(kw in s.lower() for kw in priority_keywords)
)

for url in priority_scripts:
    name = url.split("/")[-1][:50]
    status, js = fetch(url, timeout=20)
    if status != 200:
        print(f"  SKIP {status} {url}")
        continue
    grep_bundle(name, js)

# ── Paso 4: probar subdominios alternativos ────────────────────────────────
print("\n--- PROBANDO SUBDOMINIOS ALTERNATIVOS ---")
subdomains = [
    "https://api.bvl.com.pe",
    "https://api.bvl.com.pe/v1/quotes/SAGAC1",
    "https://api.bvl.com.pe/v2/quotes/SAGAC1",
    "https://services.bvl.com.pe",
    "https://market.bvl.com.pe",
    "https://data.bvl.com.pe",
    "https://ws.bvl.com.pe",
]
for url in subdomains:
    status, body = fetch(url, timeout=10)
    preview = body[:200].replace("\n", " ") if status < 400 else ""
    print(f"  {status}  {url}  {preview}")
