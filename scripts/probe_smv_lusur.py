"""SMV: identificador (RPJ, moneda, cobertura) de LUZ DEL SUR, para evaluarlo
como 7mo activo (utilities). Verifica moneda y presencia I/C 2012 y 2023."""
from __future__ import annotations
import json
from zeep import Client
from zeep.helpers import serialize_object

client = Client("https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx?WSDL")
PISTAS = ["luz del sur", "edelnor", "enel", "electro"]

for ejercicio, periodo in [(2023, 4), (2012, 4)]:
    for tipo in ["I", "C"]:
        raw = client.service.obtener_InfoFinanciera(
            Ejercicio=str(ejercicio), Periodo=str(periodo), Tipo=tipo)
        data = serialize_object(raw)
        if isinstance(data, str):
            data = json.loads(data)
        print(f"\n===== Ej={ejercicio} Per={periodo} Tipo={tipo}  ({len(data or [])} emp.) =====")
        for r in (data or []):
            nom = str(r.get("NombreEmpresa", ""))
            if any(p in nom.lower() for p in PISTAS):
                print(f"  RPJ='{r.get('RPJ')}'  Moneda='{r.get('Moneda')}'  "
                      f"UtilNeta={r.get('UtilidadNeta')}  {nom}")
