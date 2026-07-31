"""SMV: identificadores (RPJ, moneda, cobertura) de FERREYCORP y MINSUR, para
evaluarlos como reemplazos (Ferreycorp = bienes de capital; Minsur = mineria
BVL-nativa mas liquida que BVN). Verifica sobre todo la MONEDA (si reportan en
USD como BVN, complican el P/E)."""
from __future__ import annotations
import json
from zeep import Client
from zeep.helpers import serialize_object

SMV_WSDL = "https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx?WSDL"
TARGETS = {
    "FERREYCORP": ["ferreycorp", "ferreyros"],
    "MINSUR":     ["minsur"],
}


def call_op(client, ejercicio, periodo, tipo):
    raw = client.service.obtener_InfoFinanciera(
        Ejercicio=str(ejercicio), Periodo=str(periodo), Tipo=tipo)
    data = serialize_object(raw)
    if isinstance(data, str):
        data = json.loads(data)
    return data or []


client = Client(SMV_WSDL)
for ejercicio, periodo in [(2023, 4), (2012, 4)]:
    for tipo in ["I", "C"]:
        print(f"\n===== Ejercicio={ejercicio} Periodo={periodo} Tipo={tipo} =====")
        try:
            rows = call_op(client, ejercicio, periodo, tipo)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        print(f"  total empresas: {len(rows)}")
        for label, terms in TARGETS.items():
            for r in rows:
                razon = str(r.get("RazonSocial", "")).lower()
                if any(t in razon for t in terms):
                    print(f"  [{label}] RPJ='{r.get('RPJ')}'  '{r.get('RazonSocial')}'")
                    print(f"           Moneda='{r.get('Moneda')}'  "
                          f"ActivoTotal={r.get('ActivoTotal')}  "
                          f"UtilidadNeta={r.get('UtilidadNeta')}")
