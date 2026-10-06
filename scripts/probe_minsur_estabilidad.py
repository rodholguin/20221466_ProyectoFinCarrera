"""Estabilidad del capital de Minsur (A20032) 2012-2025: barre las cuentas de
patrimonio del SMV para ver si el Capital Emitido (comun, 1D0701) y las Acciones
de Inversion (1D0703) fueron planos (=> conteo estable) o si hubo emisiones/
reducciones. Minsur reporta en USD (moneda funcional), asi que un monto plano en
USD implica conteo estable (sin traduccion FX que lo mueva)."""
from __future__ import annotations
import json
from zeep import Client
from zeep.helpers import serialize_object

client = Client("https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx?WSDL")
RPJ = "A20032"
CUENTAS = {"1D0701": "Capital Emitido (comun)", "1D0703": "Acciones de Inversion",
           "1D0711": "Acciones Propias en Cartera", "1D07ST": "Total Patrimonio"}


def balance(ej, tipo):
    raw = client.service.obtener_BalanceGeneral(Ejercicio=str(ej), Periodo="4", Tipo=tipo)
    data = serialize_object(raw)
    if isinstance(data, str):
        data = json.loads(data)
    out = {}
    mon = None
    for r in (data or []):
        if r.get("RPJ") == RPJ:
            mon = r.get("Moneda")
            if r.get("Cuenta") in CUENTAS:
                out[r["Cuenta"]] = r.get("Monto1")
    return mon, out


for tipo in ["I", "C"]:
    print(f"\n===== Minsur Tipo={tipo} =====")
    print(f"{'Anio':<6} {'Moneda':<8} " + " ".join(f"{c:>12}" for c in CUENTAS))
    for ej in [2012, 2014, 2016, 2018, 2020, 2022, 2024, 2025]:
        mon, d = balance(ej, tipo)
        if not d:
            print(f"{ej:<6} (sin filas)")
            continue
        row = " ".join(f"{str(d.get(c)):>12}" for c in CUENTAS)
        print(f"{ej:<6} {str(mon):<8} {row}")
