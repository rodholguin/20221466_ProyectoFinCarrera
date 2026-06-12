"""Sonda para descubrir endpoints de datos fundamentales.

Objetivos:
  1. SMV WSDL — listar operaciones y probar llamadas reales para cada empresa
  2. BVL dataondemand — probar /v1/financialstatements/ con variantes de payload
  3. Reportar resultados listos para implementar en fundamentals_client.py
"""
from __future__ import annotations

import json
import textwrap

import requests

# ── Empresas del universo ────────────────────────────────────────────────────
UNIVERSE = [
    {"bvl": "CREDITC1",  "smv": "Banco de Credito del Peru S.A."},
    {"bvl": "BUENAVC1",  "smv": "Compañia de Minas Buenaventura S.A.A."},
    {"bvl": "ALICORC1",  "smv": "Alicorp S.A.A."},
    {"bvl": "SAGAC1",    "smv": "Saga Falabella S.A."},
    {"bvl": "CORAREC1",  "smv": "Corporacion Aceros Arequipa S.A."},
]

SMV_WSDL = "https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx?WSDL"
BVL_BASE  = "https://dataondemand.bvl.com.pe"

BVL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin":     "https://www.bvl.com.pe",
    "Referer":    "https://www.bvl.com.pe/",
    "Accept":     "application/json, text/plain, */*",
    "Accept-Language": "es-PE,es;q=0.9",
}

SEP = "=" * 70


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 1: SMV WSDL
# ─────────────────────────────────────────────────────────────────────────────
def section_smv():
    print(SEP)
    print("SECCIÓN 1 — SMV WSDL (Datos Abiertos)")
    print(SEP)
    try:
        from zeep import Client
        from zeep.helpers import serialize_object
    except ImportError:
        print("  zeep no instalado. Ejecutar: pip install zeep")
        return None

    print(f"\nCargando WSDL: {SMV_WSDL}\n")
    try:
        client = Client(SMV_WSDL)
    except Exception as exc:
        print(f"  ERROR al cargar WSDL: {exc}")
        return None

    # 1a. Listar operaciones
    ops: list[str] = []
    for svc in client.wsdl.services.values():
        for port in svc.ports.values():
            for op_name in port.binding._operations.keys():
                ops.append(op_name)

    print("Operaciones disponibles:")
    for op in ops:
        print(f"  - {op}")

    # 1b. Inspeccionar parámetros de cada operación
    print("\nParámetros por operación:")
    for svc in client.wsdl.services.values():
        for port in svc.ports.values():
            for op_name, op_obj in port.binding._operations.items():
                try:
                    body = op_obj.input.body
                    params = list(body.type.elements) if hasattr(body, "type") else []
                    param_names = [e[0] for e in params] if params else ["(sin parámetros detectados)"]
                except Exception:
                    param_names = ["(no se pudo inspeccionar)"]
                print(f"  {op_name}: {param_names}")

    # 1c. Llamadas de prueba para Alicorp (empresa no-bancaria sencilla)
    print("\n--- Pruebas de llamada: Alicorp S.A.A. ---")
    test_asset = {"bvl": "ALICORC1", "smv": "Alicorp S.A.A."}

    # Construir todas las combinaciones plausibles
    calls_to_try = []
    for op in ops:
        for tipo in ("Individual", "Consolidada", "I", "C"):
            for anio in (2023, 2022):
                for tri in (4, 3):
                    calls_to_try.append((op, test_asset["smv"], anio, tri, tipo))

    max_tries = 20  # no abusar
    tried = 0
    for op_name, smv_name, anio, tri, tipo in calls_to_try:
        if tried >= max_tries:
            break
        tried += 1
        try:
            fn = getattr(client.service, op_name)
            # Probar con nombre largo "empresa" y nombre corto "nemonico"
            for kwargs in [
                {"empresa": smv_name, "anio": str(anio), "trimestre": str(tri), "tipo": tipo},
                {"empresa": smv_name, "anio": anio, "trimestre": tri, "tipo": tipo},
                {"nemonico": test_asset["bvl"], "anio": str(anio), "trimestre": str(tri)},
            ]:
                try:
                    result = fn(**kwargs)
                    raw = serialize_object(result)
                    snippet = str(raw)[:500]
                    print(f"  OK  {op_name}({kwargs}) =>\n    {snippet}\n")
                    break
                except Exception as e:
                    err = str(e)[:120]
                    print(f"  ERR {op_name}({kwargs}): {err}")
        except Exception as outer:
            print(f"  ERR {op_name}: {outer}")

    return client


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 2: BVL dataondemand — financial statements
# ─────────────────────────────────────────────────────────────────────────────
def _bvl_req(method: str, path: str, **kwargs):
    url = BVL_BASE + path
    r = getattr(requests, method)(url, headers=BVL_HEADERS, timeout=20, **kwargs)
    ct = r.headers.get("content-type", "")
    try:
        body = r.json()
        snippet = json.dumps(body, ensure_ascii=False)[:600]
    except Exception:
        snippet = r.text[:400].replace("\n", " ")
    print(f"  {method.upper()} {r.url}")
    print(f"    status={r.status_code}  ct={ct}")
    print(f"    body={snippet}")
    print()
    return r


def section_bvl_financials():
    print(SEP)
    print("SECCIÓN 2 — BVL dataondemand: estados financieros")
    print(SEP)

    ticker = "ALICORC1"  # empresa de prueba

    # 2a. GET simple (igual que cotizaciones)
    print("\n2a. GET /v1/financialstatements/")
    for params in [
        {"nemonico": ticker},
        {"nemonico": ticker, "period": "Q"},
        {"nemonico": ticker, "type": "income"},
        {"nemonico": ticker, "year": "2023", "quarter": "4"},
    ]:
        _bvl_req("get", "/v1/financialstatements/", params=params)

    # 2b. GET con ticker en path
    print("2b. GET /v1/financialstatements/{ticker}")
    for path in [
        f"/v1/financialstatements/{ticker}",
        f"/v1/financialstatements/{ticker}/",
        f"/v1/financial-statements/{ticker}",
        f"/v1/financial-statements/{ticker}/quarterly",
        f"/v1/financial-statements/{ticker}/annual",
    ]:
        _bvl_req("get", path)

    # 2c. POST con distintos payloads
    print("2c. POST /v1/financialstatements/")
    for payload in [
        {"company": ticker, "from": "2023-01-01", "to": "2023-12-31", "period": "Q"},
        {"nemonico": ticker, "from": "2023-01-01", "to": "2023-12-31"},
        {"ticker": ticker, "year": 2023, "quarter": 4},
        {"nemonico": ticker, "anio": 2023, "trimestre": 4},
        {"emisor": ticker},
    ]:
        _bvl_req("post", "/v1/financialstatements/", json=payload)

    # 2d. Endpoints alternativos observados en bundle JS
    print("2d. Endpoints alternativos BVL")
    for path, params in [
        ("/v1/issuer/financial-summary", {"nemonico": ticker}),
        ("/v1/issuer/financials",        {"nemonico": ticker}),
        ("/v1/issuers/financials",       {"nemonico": ticker}),
        ("/v1/issuers/eeff",             {"nemonico": ticker}),
        ("/v1/issuers/financial-info",   {"nemonico": ticker}),
        ("/v1/stock-quote/financial",    {"nemonico": ticker}),
        ("/v1/fundamentals",             {"nemonico": ticker}),
        ("/v1/fundamental-data",         {"nemonico": ticker}),
        ("/v1/balance-sheet",            {"nemonico": ticker}),
        ("/v1/income-statement",         {"nemonico": ticker}),
        ("/v1/cash-flow",                {"nemonico": ticker}),
        ("/v2/financialstatements/",     {"nemonico": ticker}),
    ]:
        _bvl_req("get", path, params=params)


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 3: BVL emisores — página pública de la empresa
# ─────────────────────────────────────────────────────────────────────────────
def section_bvl_emisores():
    print(SEP)
    print("SECCIÓN 3 — BVL API pública: información de emisores")
    print(SEP)

    ticker = "ALICORC1"

    # Endpoints de info general del emisor (pueden devolver ratios)
    print("\n3a. Info del emisor")
    for path, params in [
        ("/v1/issuers/stock",            {"nemonico": ticker}),
        ("/v1/issuers/stock/",           {"nemonico": ticker}),
        ("/v1/stock-quote/share",        {"nemonico": ticker}),
        ("/v1/stock-quote/home",         {"nemonico": ticker}),
        (f"/v1/issuers/{ticker}",        None),
        (f"/v1/issuers/{ticker}/stock",  None),
        (f"/v1/issuers/{ticker}/detail", None),
    ]:
        _bvl_req("get", path, params=params)

    # Probar api.bvl.com.pe (base alternativa hallada en bundle)
    print("\n3b. api.bvl.com.pe")
    for path, params in [
        ("/v1/issuers/financials",       {"nemonico": ticker}),
        ("/v1/financialstatements/",     {"nemonico": ticker}),
        (f"/v1/issuers/{ticker}",        None),
    ]:
        url = "https://api.bvl.com.pe" + path
        try:
            r = requests.get(url, headers=BVL_HEADERS, params=params, timeout=15)
            ct = r.headers.get("content-type", "")
            try:
                body = json.dumps(r.json(), ensure_ascii=False)[:500]
            except Exception:
                body = r.text[:300].replace("\n", " ")
            print(f"  GET {r.url}")
            print(f"    status={r.status_code}  ct={ct}")
            print(f"    body={body}")
            print()
        except Exception as exc:
            print(f"  GET {url}: ERROR {exc}\n")


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 4: SMV portal web — datos abiertos REST (alternativa al SOAP)
# ─────────────────────────────────────────────────────────────────────────────
def section_smv_rest():
    print(SEP)
    print("SECCIÓN 4 — SMV datos abiertos REST / portal")
    print(SEP)

    # El portal SMV expone un API REST además del SOAP
    SMV_REST_BASES = [
        "https://www.smv.gob.pe",
        "https://www.smv.gob.pe/Frm_InformacionFinanciera",
        "https://datosabiertos.smv.gob.pe",
        "https://mvnet.smv.gob.pe",
    ]

    empresa = "Alicorp S.A.A."
    empresa_enc = requests.utils.quote(empresa)

    test_paths = [
        f"/api/v1/eeff?empresa={empresa_enc}&anio=2023&trimestre=4",
        f"/api/eeff?empresa={empresa_enc}&anio=2023",
        f"/ws_od_eeff/WebServiceInfoFinanciera.asmx/obtener_GanciaPerdida"
        f"?empresa={empresa_enc}&anio=2023&trimestre=4&tipo=Individual",
        "/ws_od_eeff/WebServiceInfoFinanciera.asmx/ObtenerListaEmpresas",
    ]

    for base in SMV_REST_BASES:
        for path in test_paths:
            url = base + path
            try:
                r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                ct = r.headers.get("content-type", "")
                body = r.text[:300].replace("\n", " ")
                print(f"  GET {url}")
                print(f"    status={r.status_code}  ct={ct}")
                print(f"    body={body}")
                print()
            except Exception as exc:
                print(f"  GET {url}: ERROR {exc}\n")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    run = set(sys.argv[1:]) or {"smv", "bvl", "emisores", "smv_rest"}

    if "smv" in run:
        section_smv()
    if "bvl" in run:
        section_bvl_financials()
    if "emisores" in run:
        section_bvl_emisores()
    if "smv_rest" in run:
        section_smv_rest()

    print(SEP)
    print("FIN DEL SONDEO")
    print(SEP)
    print(textwrap.dedent("""
    Próximos pasos según resultados:
      SMV OK   → implementar bucle trimestral en fetch_smv() con operaciones reales
      BVL OK   → fijar payload en fetch_bvl_dataondemand()
      Todo 4xx → revisar headers / autenticación / base URL alternativa
    """))
