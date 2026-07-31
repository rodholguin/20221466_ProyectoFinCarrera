"""Descubre el bvl_company_code (cc) y el valor nominal de los 4 activos nuevos
(INRETC1, CPACASC1, FERREYC1, LUSURC1) para poder agregarlos a config.yaml.

El cc abre /v1/issuers/{cc}/value -> listStock (nominalValue, quantity=acciones en
circulacion) + listBenefit (dividendos/acciones liberadas, fuente de R3). Ver
scripts/probe_bvl_capital.py. Primero se busca el cc en el listado de emisores.
"""
from __future__ import annotations
import json
import requests

DOD = "https://dataondemand.bvl.com.pe"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": "https://www.bvl.com.pe",
    "Referer": "https://www.bvl.com.pe/",
    "Accept": "application/json, text/plain, */*",
}
TARGET_NEMOS = {"INRETC1", "CPACASC1", "FERREYC1", "LUSURC1"}
# incumbentes conocidos, para validar que el mapeo nemonico->cc funciona
KNOWN = {"CREDITC1": "12000", "BUENAVC1": "61200", "ALICORC1": "21400",
         "SAGAC1": "75700", "CORAREC1": "20601"}


def get(path, params=None):
    try:
        r = requests.get(DOD + path, headers=HEADERS, params=params, timeout=40)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text[:200]
    except Exception as e:
        return None, f"EXC {e}"


# 1) Buscar el listado de emisores. Probar endpoints candidatos.
print("=== Buscando listado de emisores ===")
found_list = None
for path, params in [
    ("/v1/issuers", None),
    ("/v1/issuers", {"page": 0, "size": 2000}),
    ("/v1/companies", None),
    ("/v1/stock-quote/companies", None),
    ("/v1/issuers/search", {"search": ""}),
]:
    st, body = get(path, params)
    n = len(body) if isinstance(body, list) else (
        f"dict:{list(body.keys())[:6]}" if isinstance(body, dict) else str(body)[:60])
    print(f"GET {path} {params or ''} -> {st}  {n}")
    if isinstance(body, list) and body:
        found_list = body
        print("   claves item[0]:", list(body[0].keys()) if isinstance(body[0], dict) else type(body[0]))
        break
    if isinstance(body, dict):
        for key in ("content", "data", "items", "issuers"):
            if isinstance(body.get(key), list) and body[key]:
                found_list = body[key]
                print(f"   -> lista en body['{key}'], claves:", list(found_list[0].keys()))
                break
        if found_list:
            break

# 2) Extraer cc de los targets (+ validar con un incumbente)
if found_list:
    print("\n=== Mapeo nemonico -> company code ===")
    wanted = TARGET_NEMOS | {"CREDITC1"}  # CREDITC1 para validar (debe dar 12000)
    for item in found_list:
        blob = json.dumps(item, ensure_ascii=False).upper()
        for nemo in list(wanted):
            if nemo in blob:
                print(f"  {nemo}:")
                print("   ", json.dumps(item, ensure_ascii=False)[:400])
                wanted.discard(nemo)
    if wanted:
        print("  NO encontrados:", wanted)
else:
    print("\nNo se halló listado; probar dump del bundle o inspeccionar /v1/issuers manualmente.")
