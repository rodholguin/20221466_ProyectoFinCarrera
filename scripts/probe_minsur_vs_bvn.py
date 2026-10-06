"""Metricas de comparacion BVN (BUENAVC1) vs Minsur (MINSURI1) para decidir la
minera del universo. Reune: company code BVL, valor nominal, acciones (snapshot),
dividendos, moneda del precio, y utilidad neta anual del SMV (frecuencia de
perdidas -> cobertura de P/E). Ambas reportan en USD (Moneda='Dolares').
"""
from __future__ import annotations
import json
import requests
from zeep import Client
from zeep.helpers import serialize_object

DOD = "https://dataondemand.bvl.com.pe"
H = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.bvl.com.pe",
     "Referer": "https://www.bvl.com.pe/", "Accept": "application/json"}


def get(path, params=None):
    r = requests.get(DOD + path, headers=H, params=params, timeout=40)
    try:
        return r.json()
    except Exception:
        return None


# --- 1. company code de Minsur (BVN ya se sabe: 61200) ---
issuers = get("/v1/issuers")
cc_minsur = None
for it in issuers or []:
    if "MINSUR" in json.dumps(it, ensure_ascii=False).upper():
        cc_minsur = it.get("companyCode")
        print(f"Minsur: companyCode={cc_minsur}  rpj={it.get('rpjCode')}  "
              f"sector={it.get('description')}  {it.get('companyName')}")
CODES = {"BUENAVC1": "61200", "MINSURI1": cc_minsur}

# --- 2. /value: nominal, quantity, dividendos ---
for nemo, cc in CODES.items():
    if not cc:
        continue
    body = get(f"/v1/issuers/{cc}/value")
    print(f"\n=== {nemo} (cc={cc}) ===")
    for v in (body or []):
        if v.get("nemonico") not in (nemo, None):
            continue
        for row in (v.get("listStock") or []):
            print(f"  STOCK nemo={row.get('nemonico')} quantity={row.get('quantity')} "
                  f"coin={row.get('coin')} nominal={row.get('nominalValue')}")
        tipos = {}
        for b in (v.get("listBenefit") or []):
            t = b.get("description")
            tipos[t] = tipos.get(t, 0) + 1
        if tipos:
            print(f"  BENEFIT {v.get('nemonico')}: {json.dumps(tipos, ensure_ascii=False)}")

# --- 3. moneda del precio (muestra reciente) ---
print("\n=== Moneda del precio (share-values 2025) ===")
for nemo in ["BUENAVC1", "MINSURI1"]:
    r = requests.get(f"{DOD}/v1/stock-quote/share-values/{nemo}",
                     params={"startDate": "2025-12-01", "endDate": "2025-12-31"},
                     headers=H, timeout=30)
    vals = r.json().get("values", [])
    print(f"  {nemo}: {vals[-2:] if vals else 'sin datos'}")

# --- 4. Utilidad neta anual SMV (perdidas -> P/E NaN) ---
print("\n=== Utilidad Neta anual SMV (Consolidado, miles USD) ===")
client = Client("https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx?WSDL")
RPJ = {"BUENAVC1": "B20003", "MINSURI1": "A20032"}
print(f"{'Anio':<6} {'BUENAVC1':>14} {'MINSURI1':>14}")
for ej in [2013, 2015, 2017, 2019, 2020, 2021, 2022, 2023, 2024]:
    raw = client.service.obtener_InfoFinanciera(Ejercicio=str(ej), Periodo="4", Tipo="C")
    data = serialize_object(raw)
    if isinstance(data, str):
        data = json.loads(data)
    un = {}
    for r in (data or []):
        if r.get("RPJ") in RPJ.values():
            un[r["RPJ"]] = r.get("UtilidadNeta")
    print(f"{ej:<6} {str(un.get('B20003')):>14} {str(un.get('A20032')):>14}")
