"""Descubre identificadores SMV (RPJ, Moneda, cobertura) de los candidatos
INRETAIL y PACASMAYO, para poder agregarlos al universo (config.yaml).
"""
from __future__ import annotations
import json

from zeep import Client
from zeep.helpers import serialize_object

SMV_WSDL = "https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx?WSDL"

TARGETS = {
    "INRETAIL":  ["inretail", "supermercados peruanos", "intercorp retail"],
    "PACASMAYO": ["pacasmayo"],
}


def call_op(client, ejercicio, periodo, tipo):
    raw = client.service.obtener_InfoFinanciera(
        Ejercicio=str(ejercicio), Periodo=str(periodo), Tipo=tipo)
    data = serialize_object(raw)
    if isinstance(data, str):
        data = json.loads(data)
    return data or []


client = Client(SMV_WSDL)

# Barrido de tipo (I=Individual, C=Consolidado) en un trimestre reciente y uno
# antiguo, para ver moneda y cobertura.
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
            hits = [r for r in rows
                    if any(t in (r.get("NombreEmpresa") or "").lower() for t in terms)]
            for m in hits:
                print(f"  [{label}] RPJ={m.get('RPJ')!r}  {m.get('NombreEmpresa')!r}")
                print(f"           Moneda={m.get('Moneda')!r}  "
                      f"ActivoTotal={m.get('ActivoTotal')}  "
                      f"UtilidadNeta={m.get('UtilidadNeta')}")
            if not hits:
                print(f"  [{label}] sin coincidencias")
