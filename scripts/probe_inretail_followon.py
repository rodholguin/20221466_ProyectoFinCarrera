"""Fija el trimestre exacto del follow-on de InRetail: barre el Capital Emitido
(cuenta SMV 1D0701, Individual) por trimestre 2020-2022 para ubicar el salto
2,739,714 -> 2,962,923 (miles de S/). Tambien vuelca Acciones en Cartera (1D0711)."""
from __future__ import annotations
import json
from zeep import Client
from zeep.helpers import serialize_object

client = Client("https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx?WSDL")
RPJ = "OE5087"


def cap_emitido(ej, per):
    raw = client.service.obtener_BalanceGeneral(
        Ejercicio=str(ej), Periodo=str(per), Tipo="I")
    data = serialize_object(raw)
    if isinstance(data, str):
        data = json.loads(data)
    out = {}
    for r in (data or []):
        if r.get("RPJ") == RPJ and r.get("Cuenta") in ("1D0701", "1D0711"):
            out[r["Cuenta"]] = r.get("Monto1")
    return out


print(f"{'Periodo':<10} {'CapEmitido(1D0701)':>20} {'AccCartera(1D0711)':>20}")
for ej in [2020, 2021, 2022]:
    for per in [1, 2, 3, 4]:
        d = cap_emitido(ej, per)
        print(f"{ej}-Q{per:<6} {str(d.get('1D0701')):>20} {str(d.get('1D0711')):>20}")
