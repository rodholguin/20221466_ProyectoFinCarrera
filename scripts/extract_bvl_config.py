"""Extrae API_URL, API_URL_2 y tokens del bundle main.js de la BVL."""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Referer": "https://www.bvl.com.pe/",
}

print("Descargando main.js...")
r = requests.get("https://www.bvl.com.pe/main.1ca3dd889220439bbef2.js", headers=HEADERS, timeout=30)
js = r.text
print(f"OK  {len(js)//1024}KB\n")

# ── API_URL y API_URL_2 ──────────────────────────────────────────────────────
print("=== API_URL / API_URL_2 ===")
for kw in ["API_URL", "API_URL_2", "apiUrl", "apiUrl2", "API_BASE", "BASE_URL", "baseUrl"]:
    for m in re.finditer(re.escape(kw) + r'\s*[=:]\s*["\`]([^"\`\s]{10,120})["\`]', js):
        print(f"  {kw} = {m.group(1)}")

# Buscar objetos de entorno: {API_URL:"...",API_URL_2:"...",...}
env_blocks = re.findall(r'\{[^{}]{0,500}API_URL[^{}]{0,500}\}', js)
for b in env_blocks[:5]:
    print(f"\n  env-block: {b[:500]}")

# ── X-Api-Key / keys embebidas ───────────────────────────────────────────────
print("\n=== KEYS / AUTH ===")
for kw in ["X-Api-Key", "x-api-key", "ApiKey", "apiKey", "x_api_key", "api_key"]:
    for m in re.finditer(re.escape(kw), js, re.I):
        ctx = js[max(0, m.start()-80):m.end()+200]
        print(f"  [{kw}] {ctx}")

# ── Buscar tokens hardcodeados (UUID o base64 largos) ───────────────────────
print("\n=== POSIBLES TOKENS ===")
# UUID pattern
uuids = re.findall(r'["\`]([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})["\`]', js)
print(f"  UUIDs encontrados: {uuids[:10]}")

# Strings largos que parezcan tokens (30+ chars alfanuméricos)
tokens = re.findall(r'["\`]([A-Za-z0-9+/=_\-]{32,120})["\`]', js)
filtered = [t for t in tokens if len(set(t)) > 10]  # excluir repetitivos
print(f"  Posibles tokens ({len(filtered)} total): {filtered[:15]}")

# ── Buscar el bloque de configuración de entorno Angular ─────────────────────
print("\n=== ENVIRONMENT BLOCK ===")
# Angular compila environment.ts como: Object.defineProperty(e,"__esModule",...) o como e.production=!0
env_patterns = [
    r'e\.production\s*=',
    r'production\s*:\s*(?:!0|true)',
    r'environment\s*=\s*\{',
]
for pat in env_patterns:
    for m in re.finditer(pat, js):
        ctx = js[m.start():m.start()+600]
        print(f"  [{pat}] {ctx[:600]}")

# ── Buscar cualquier URL de api.bvl.com.pe en el bundle ─────────────────────
print("\n=== URLs api.bvl.com.pe ===")
urls = re.findall(r'["\`](https?://api\.bvl\.com\.pe[^"\`\s<>]{0,100})["\`]', js)
for u in set(urls):
    print(f"  {u}")

# ── Buscar 'w=' y 'C=' justo antes del bloque de rutas ──────────────────────
print("\n=== VARIABLES w y C (base URLs) ===")
for kw in ['w=i.a.API_URL', 'C=i.a.API_URL', 'w=n.API_URL', 'C=n.API_URL',
           'w=t.API_URL', 'C=t.API_URL']:
    if kw in js:
        pos = js.index(kw)
        print(f"  {kw}  ctx={js[max(0,pos-200):pos+300]}")
