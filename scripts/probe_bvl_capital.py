"""Sondeo BVL — ¿el 'Listado de Capital en Circulacion' se sirve desde
dataondemand.bvl.com.pe? (jul-2026)

Objetivo: confirmar si la BVL expone, en el MISMO endpoint no documentado que ya
usamos para precios y acciones corporativas, el numero de acciones representativas
del capital social por emisor (= acciones en circulacion). Ese dato es el unico
insumo faltante para P/E y Dividend Yield (ver docs/hallazgos_fundamentales_R4.txt
seccion 5.8). De existir, seria la fuente autoritativa y gratuita, evitando EODHD.

Estrategia:
  1. Volcar TODO el detalle del emisor (/v1/issuers/{cc}) y su /value para ver si
     el numero de acciones / capital ya viene embebido (campos como
     nominalValue, capital, shares, listedShares, quantity, etc.).
  2. Probar una bateria de endpoints candidatos para 'capital en circulacion'.
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

COMPANY_CODE = {
    "CREDITC1": "12000",
    "BUENAVC1": "61200",
    "ALICORC1": "21400",
    "SAGAC1":   "75700",
    "CORAREC1": "20601",
}


def try_get(path: str, params: dict | None = None):
    url = DOD + path
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=40)
        body = None
        try:
            body = r.json()
        except Exception:
            body = r.text[:300]
        return r.status_code, body
    except Exception as exc:
        return None, f"EXC: {exc}"


def try_post(path: str, payload: dict):
    url = DOD + path
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=40)
        body = None
        try:
            body = r.json()
        except Exception:
            body = r.text[:300]
        return r.status_code, body
    except Exception as exc:
        return None, f"EXC: {exc}"


def dump_issuer_detail(cc: str):
    print(f"\n{'='*70}\n=== /v1/issuers/{cc}  (detalle del emisor) ===")
    st, body = try_get(f"/v1/issuers/{cc}")
    print(f"HTTP {st}")
    if isinstance(body, dict):
        # Mostrar claves de primer nivel y listValue completo (ahi vive el capital)
        print("claves nivel-0:", list(body.keys()))
        for v in body.get("listValue") or []:
            print("  listValue item:", json.dumps(v, ensure_ascii=False)[:800])
    else:
        print(body)


def dump_value(cc: str):
    print(f"\n=== /v1/issuers/{cc}/value  (claves, sin listBenefit) ===")
    st, body = try_get(f"/v1/issuers/{cc}/value")
    print(f"HTTP {st}")
    if isinstance(body, list):
        for v in body:
            slim = {k: val for k, val in v.items() if k != "listBenefit"}
            print("  ", json.dumps(slim, ensure_ascii=False)[:800])


CANDIDATE_GET = [
    "/v1/issuers/{cc}/shares",
    "/v1/issuers/{cc}/capital",
    "/v1/issuers/{cc}/shares-outstanding",
    "/v1/issuers/{cc}/capital-stock",
    "/v1/issuers/{cc}/listed-capital",
    "/v1/issuers/{cc}/circulating-capital",
    "/v1/capital-in-circulation",
    "/v1/listed-capital",
    "/v1/share-capital",
    "/v1/circulating-capital",
    "/v1/outstanding-shares",
    "/v1/stock-quote/capital/{nemo}",
    "/v1/stock-quote/shares/{nemo}",
]

CANDIDATE_POST = [
    ("/v1/capital-in-circulation", {"nemonico": "{nemo}"}),
    ("/v1/listed-capital", {"companyCode": "{cc}"}),
    ("/v1/circulating-capital", {"companyCode": "{cc}"}),
]


def probe_candidates():
    nemo, cc = "CREDITC1", COMPANY_CODE["CREDITC1"]
    print(f"\n{'='*70}\n=== ENDPOINTS CANDIDATOS (CREDITC1 cc={cc}) ===")
    for tmpl in CANDIDATE_GET:
        path = tmpl.replace("{cc}", cc).replace("{nemo}", nemo)
        st, body = try_get(path)
        summ = body if isinstance(body, (str, type(None))) else (
            f"list[{len(body)}]" if isinstance(body, list)
            else ("null-body" if body is None else f"dict keys={list(body.keys())[:8]}")
        )
        flag = "  <-- REVISAR" if (st == 200 and body not in (None, [], "")) else ""
        print(f"GET  {path:52} -> {st}  {str(summ)[:80]}{flag}")
    for tmpl, payload_tmpl in CANDIDATE_POST:
        payload = {k: v.replace("{cc}", cc).replace("{nemo}", nemo)
                   for k, v in payload_tmpl.items()}
        st, body = try_post(tmpl, payload)
        summ = body if isinstance(body, (str, type(None))) else f"{type(body).__name__}"
        print(f"POST {tmpl:52} {payload} -> {st}  {str(summ)[:70]}")


def dump_liststock_all():
    """El hallazgo: /v1/issuers/{cc}/value trae listStock con quantity (acciones
    en circulacion), capital y nominalValue. Ver cobertura para los 5 activos y
    si listStock es un snapshot unico o una serie historica."""
    print(f"\n{'='*70}\n=== listStock (capital en circulacion) — los 5 activos ===")
    for nemo, cc in COMPANY_CODE.items():
        st, body = try_get(f"/v1/issuers/{cc}/value")
        if not isinstance(body, list):
            print(f"{nemo}: HTTP {st} (no-list)")
            continue
        for v in body:
            ls = v.get("listStock") or []
            vn = v.get("nemonico")
            print(f"\n{nemo} (value item nemonico={vn}): listStock n={len(ls)}")
            for row in ls:
                print("   ", json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    dump_issuer_detail(COMPANY_CODE["CREDITC1"])
    dump_value(COMPANY_CODE["CREDITC1"])
    probe_candidates()
    dump_liststock_all()
