"""Sonda 2: parámetros correctos según el WSDL real.

SMV: Ejercicio, Periodo, Tipo  (no empresa/anio/trimestre)
BVL: endpoints con 200-null necesitan parámetros distintos
"""
from __future__ import annotations
import json
import sys
import requests

UNIVERSE = [
    {"bvl": "CREDITC1",  "smv": "Banco de Credito del Peru S.A."},
    {"bvl": "BUENAVC1",  "smv": "Compañia de Minas Buenaventura S.A.A."},
    {"bvl": "ALICORC1",  "smv": "Alicorp S.A.A."},
    {"bvl": "SAGAC1",    "smv": "Saga Falabella S.A."},
    {"bvl": "CORAREC1",  "smv": "Corporacion Aceros Arequipa S.A."},
]
SMV_WSDL = "https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx?WSDL"
BVL_BASE  = "https://dataondemand.bvl.com.pe"
SEP = "=" * 70

BVL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin":     "https://www.bvl.com.pe",
    "Referer":    "https://www.bvl.com.pe/",
    "Accept":     "application/json, text/plain, */*",
    "Accept-Language": "es-PE,es;q=0.9",
}


def pp(obj, limit=1500):
    """Pretty-print con limite."""
    s = json.dumps(obj, ensure_ascii=False, indent=2) if isinstance(obj, (dict, list)) else str(obj)
    if len(s) > limit:
        s = s[:limit] + f"\n... [truncado, total {len(str(obj))} chars]"
    print(s)


# =============================================================================
# SECCION A: SMV — parámetros correctos Ejercicio/Periodo/Tipo
# =============================================================================
def section_smv_correct():
    print(SEP)
    print("SECCION A -- SMV con parametros correctos: Ejercicio/Periodo/Tipo")
    print(SEP)
    try:
        from zeep import Client
        from zeep.helpers import serialize_object
    except ImportError:
        print("  pip install zeep")
        return

    client = Client(SMV_WSDL)

    OPS_PRINCIPALES = [
        "obtener_BalanceGeneral",
        "obtener_GanciaPerdida",
        "obtener_ResultadosIntegrales",
        "obtener_FlujoEfectivo",
        "obtener_InfoFinanciera",
    ]

    # Valores a probar para Periodo
    PERIODO_OPTS = ["4", "T4", "4T", "IV", "Q4", "A", "Anual", "04"]
    TIPO_OPTS    = ["I", "C", "Individual", "Consolidada"]

    print("\nA1. Llamadas sin filtro de empresa (Ejercicio=2023, distintos Periodo/Tipo)")
    print("    (si devuelve datos masivos, el filtro se hace en cliente)\n")

    found_working = []
    for op_name in ["obtener_BalanceGeneral", "obtener_GanciaPerdida"]:
        fn = getattr(client.service, op_name)
        for periodo in PERIODO_OPTS:
            for tipo in TIPO_OPTS[:2]:
                try:
                    result = fn(Ejercicio="2023", Periodo=periodo, Tipo=tipo)
                    raw = serialize_object(result)
                    raw_str = str(raw)
                    if raw is not None and raw_str not in ("None", "{}", "[]", ""):
                        print(f"  OK  {op_name}(Ejercicio='2023', Periodo='{periodo}', Tipo='{tipo}')")
                        pp(raw)
                        found_working.append((op_name, "2023", periodo, tipo))
                        break
                    else:
                        print(f"  NULL {op_name}(Periodo='{periodo}', Tipo='{tipo}')")
                except Exception as e:
                    print(f"  ERR  {op_name}(Periodo='{periodo}', Tipo='{tipo}'): {str(e)[:100]}")
            if found_working:
                break

    # Si encontramos parámetros que funcionan, probar todas las operaciones
    if found_working:
        print("\nA2. Todas las operaciones con parametros validados")
        _, ej, per, tip = found_working[0]
        for op_name in OPS_PRINCIPALES:
            fn = getattr(client.service, op_name)
            try:
                result = fn(Ejercicio=ej, Periodo=per, Tipo=tip)
                raw = serialize_object(result)
                print(f"\n  {op_name}:")
                pp(raw, limit=800)
            except Exception as e:
                print(f"  ERR {op_name}: {str(e)[:120]}")

    # obtener_EFData tiene firma distinta: page, rows, sidx, sord, _search
    print("\nA3. obtener_EFData (firma diferente: page/rows/sidx/sord/_search)")
    fn = client.service.obtener_EFData
    for kwargs in [
        {"page": 1, "rows": 5, "sidx": "", "sord": "asc", "_search": False},
        {"page": 1, "rows": 5, "sidx": "empresa", "sord": "asc", "_search": True},
        {"page": 1, "rows": 100, "sidx": "", "sord": "asc", "_search": False},
    ]:
        try:
            result = fn(**kwargs)
            raw = serialize_object(result)
            if raw is not None and str(raw) not in ("None", "{}"):
                print(f"  OK  obtener_EFData({kwargs})")
                pp(raw, limit=1000)
                break
            else:
                print(f"  NULL obtener_EFData({kwargs})")
        except Exception as e:
            print(f"  ERR obtener_EFData({kwargs}): {str(e)[:150]}")

    # Inspeccionar la respuesta XML cruda de una llamada (para entender la estructura)
    print("\nA4. Inspeccion XML crudo de obtener_BalanceGeneral")
    try:
        from zeep.transports import Transport
        from requests import Session
        session = Session()
        transport = Transport(session=session)
        client2 = Client(SMV_WSDL, transport=transport)
        # Hacer la llamada con el primer periodo que funcionó
        per0 = found_working[0][2] if found_working else "4"
        tip0 = found_working[0][3] if found_working else "I"
        with client2.settings(raw_response=True):
            resp = client2.service.obtener_BalanceGeneral(
                Ejercicio="2023", Periodo=per0, Tipo=tip0)
            print("  Content-Type:", resp.headers.get("content-type", ""))
            print("  Status:", resp.status_code)
            print("  Body (primeros 2000 chars):")
            print(resp.text[:2000])
    except Exception as e:
        print(f"  ERR XML crudo: {e}")


# =============================================================================
# SECCION B: BVL — endpoints 200-null con variantes de params
# =============================================================================
def section_bvl_200null():
    print()
    print(SEP)
    print("SECCION B -- BVL endpoints que devolvieron 200-null")
    print(SEP)

    def get(path, **kwargs):
        url = BVL_BASE + path
        r = requests.get(url, headers=BVL_HEADERS, timeout=15, **kwargs)
        ct = r.headers.get("content-type", "")
        try:
            body = r.json()
            body_str = json.dumps(body, ensure_ascii=False)[:600]
        except Exception:
            body_str = r.text[:400].replace("\n", " ")
        print(f"  {r.status_code}  {r.url}")
        print(f"    body={body_str}")
        print()
        return r

    ticker = "ALICORC1"

    print("\nB1. /v1/issuers/financials - variantes de params")
    for params in [
        {"nemonico": ticker},
        {"simbolo": ticker},
        {"ticker": ticker},
        {"code": ticker},
        {"issuer": ticker},
        {"nemonico": ticker, "period": "Q"},
        {"nemonico": ticker, "year": "2023"},
        {"nemonico": ticker, "year": "2023", "quarter": "4"},
        {"nemonico": ticker, "ejercicio": "2023", "periodo": "4"},
        {"nemonico": ticker, "anio": "2023", "trimestre": "4"},
        {},  # sin params
    ]:
        get("/v1/issuers/financials", params=params)

    print("\nB2. /v1/issuers/eeff - variantes")
    for params in [
        {"nemonico": ticker},
        {"nemonico": ticker, "type": "balance"},
        {"nemonico": ticker, "type": "income"},
        {"nemonico": ticker, "tipo": "BG"},
        {"nemonico": ticker, "tipo": "GP"},
    ]:
        get("/v1/issuers/eeff", params=params)

    print("\nB3. /v1/issuers/financial-info - variantes")
    for params in [
        {"nemonico": ticker},
        {"nemonico": ticker, "type": "quarterly"},
        {"nemonico": ticker, "frequency": "Q"},
    ]:
        get("/v1/issuers/financial-info", params=params)

    print("\nB4. Variantes con ticker en el path")
    for path in [
        f"/v1/issuers/{ticker}/financials",
        f"/v1/issuers/{ticker}/eeff",
        f"/v1/issuers/{ticker}/financial-info",
        f"/v1/issuers/{ticker}/financial-summary",
        f"/v1/issuers/{ticker}/ratios",
        f"/v1/issuers/{ticker}/indicators",
    ]:
        get(path)

    print("\nB5. Probar todos los tickers en /v1/issuers/financials")
    for asset in UNIVERSE:
        get("/v1/issuers/financials", params={"nemonico": asset["bvl"]})


# =============================================================================
# SECCION C: SMV portal web - alternativa REST HTTP
# =============================================================================
def section_smv_portal():
    print()
    print(SEP)
    print("SECCION C -- SMV portal web (alternativa REST)")
    print(SEP)

    EMPRESA = "Alicorp S.A.A."
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}

    # El portal smv.gob.pe tiene una sección de EEFF con XHR que puede ser REST
    urls = [
        ("GET", "https://www.smv.gob.pe/Frm_InformacionFinanciera",
         {"nemonico": "ALICORC1"}),
        ("GET", "https://www.smv.gob.pe/Frm_InformacionFinanciera",
         {"empresa": EMPRESA, "anio": "2023", "trimestre": "4", "tipo": "I"}),
        # El WSDL también expone endpoints HTTP básicos (sin SOAP envelope)
        ("GET",
         "https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx/obtener_BalanceGeneral",
         {"Ejercicio": "2023", "Periodo": "4", "Tipo": "I"}),
        ("GET",
         "https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx/obtener_GanciaPerdida",
         {"Ejercicio": "2023", "Periodo": "4", "Tipo": "I"}),
        ("GET",
         "https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx/obtener_InfoFinanciera",
         {"Ejercicio": "2023", "Periodo": "4", "Tipo": "I"}),
        # Probar con parametros distintos en el endpoint REST del WSDL
        ("GET",
         "https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx/obtener_BalanceGeneral",
         {"Ejercicio": "2023", "Periodo": "T4", "Tipo": "I"}),
        ("GET",
         "https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx/obtener_BalanceGeneral",
         {"Ejercicio": "2023", "Periodo": "A", "Tipo": "I"}),
    ]

    for method, url, params in urls:
        try:
            fn = getattr(requests, method.lower())
            r = fn(url, params=params, headers=headers, timeout=15)
            ct = r.headers.get("content-type", "")
            body = r.text[:600].replace("\n", " ")
            print(f"  {method} {r.url}")
            print(f"    status={r.status_code}  ct={ct}")
            print(f"    body={body}")
            print()
        except Exception as exc:
            print(f"  {method} {url}: ERROR {exc}\n")


# =============================================================================
if __name__ == "__main__":
    secs = set(sys.argv[1:]) or {"smv", "bvl", "portal"}
    if "smv"    in secs: section_smv_correct()
    if "bvl"    in secs: section_bvl_200null()
    if "portal" in secs: section_smv_portal()
    print("\n" + SEP)
    print("FIN")
