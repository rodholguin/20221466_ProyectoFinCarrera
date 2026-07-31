"""Investiga el ancla de acciones de InRetail (holding Panama, sin valor nominal,
precio en US$). Consulta el BALANCE detallado del SMV (obtener_BalanceGeneral)
para OE5087 en varios anios y vuelca las cuentas de PATRIMONIO/CAPITAL, a ver si
el numero de acciones o el capital emitido es estable 2012-2025 (=> ancla
constante defendible como BVN) o si varia."""
from __future__ import annotations
import json
from zeep import Client
from zeep.helpers import serialize_object

client = Client("https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx?WSDL")
RPJ = "OE5087"  # InRetail Peru Corp


def call(op, ej, per, tipo):
    fn = getattr(client.service, op)
    raw = fn(Ejercicio=str(ej), Periodo=str(per), Tipo=tipo)
    data = serialize_object(raw)
    if isinstance(data, str):
        data = json.loads(data)
    return data or []


# 1) Ver estructura de una fila del balance detallado (claves reales)
sample = call("obtener_BalanceGeneral", 2023, 4, "C")
mine = [r for r in sample if r.get("RPJ") == RPJ]
print(f"obtener_BalanceGeneral 2023-4 C: total filas={len(sample)}, InRetail={len(mine)}")
if mine:
    print("claves fila:", list(mine[0].keys()))

# 2) Volcar cuentas de patrimonio/capital de InRetail por anio (I y C)
KW = ["capital", "accion", "patrimonio", "emitid", "cartera", "tesor"]
for ej in [2012, 2015, 2020, 2023, 2025]:
    for tipo in ["I", "C"]:
        rows = call("obtener_BalanceGeneral", ej, 4, tipo)
        mine = [r for r in rows if r.get("RPJ") == RPJ]
        if not mine:
            continue
        print(f"\n=== InRetail {ej}-Q4 Tipo={tipo}  (moneda='{mine[0].get('Moneda')}') ===")
        for r in mine:
            desc = str(r.get("DescripcionCuenta") or "")
            cuenta = r.get("Cuenta")
            if any(k in desc.lower() for k in KW):
                print(f"  {cuenta}  {desc[:48]:48} Monto1={r.get('Monto1')}")
