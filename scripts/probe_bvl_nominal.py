"""Extrae valor nominal + acciones en circulacion (listStock) y disponibilidad de
dividendos (listBenefit) de los 4 activos nuevos, desde /v1/issuers/{cc}/value.
Cierra los datos por-activo para config.yaml (nominal_value, bvl_company_code)."""
from __future__ import annotations
import json
import requests

DOD = "https://dataondemand.bvl.com.pe"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
           "Origin": "https://www.bvl.com.pe", "Referer": "https://www.bvl.com.pe/",
           "Accept": "application/json, text/plain, */*"}
NEW = {"INRETC1": "74222", "CPACASC1": "23950", "FERREYC1": "73600", "LUSURC1": "70252"}


def get(path):
    r = requests.get(DOD + path, headers=HEADERS, timeout=40)
    try:
        return r.json()
    except Exception:
        return None


for nemo, cc in NEW.items():
    print(f"\n{'='*60}\n{nemo}  (cc={cc})")
    body = get(f"/v1/issuers/{cc}/value")
    if not isinstance(body, list):
        print("  sin /value (no-list)")
        continue
    for v in body:
        vn = v.get("nemonico")
        ls = v.get("listStock") or []
        lb = v.get("listBenefit") or []
        print(f"  value nemonico={vn}  listStock n={len(ls)}  listBenefit n={len(lb)}")
        for row in ls:
            print("    STOCK:", json.dumps(row, ensure_ascii=False))
        # muestra tipos de beneficio (dividendos/acciones liberadas) disponibles
        tipos = {}
        for b in lb:
            t = b.get("description") or b.get("benefitType") or b.get("type")
            tipos[t] = tipos.get(t, 0) + 1
        if tipos:
            print("    BENEFIT tipos:", json.dumps(tipos, ensure_ascii=False))
