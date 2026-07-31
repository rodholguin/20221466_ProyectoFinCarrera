"""Debug: lista razones sociales del SMV que contengan pistas de FERREYCORP o
MINSUR (u otras mineras/bienes de capital) para hallar su RPJ y moneda."""
from __future__ import annotations
import json
from zeep import Client
from zeep.helpers import serialize_object

client = Client("https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx?WSDL")
PISTAS = ["ferrey", "minsur", "estano", "estaño", "buenaventura", "volcan",
          "nexa", "cerro verde", "unacem", "engie"]

for tipo in ["I", "C"]:
    raw = client.service.obtener_InfoFinanciera(Ejercicio="2023", Periodo="4", Tipo=tipo)
    data = serialize_object(raw)
    if isinstance(data, str):
        data = json.loads(data)
    print(f"\n===== Tipo={tipo}  ({len(data)} empresas) =====")
    if data:
        print(f"  claves disponibles: {list(data[0].keys())}")
    for r in (data or []):
        razon = str(r.get("NombreEmpresa", "") or r.get("RazonSocial", ""))
        low = razon.lower()
        if any(p in low for p in PISTAS):
            print(f"  RPJ='{r.get('RPJ')}'  Moneda='{r.get('Moneda')}'  {razon}")
