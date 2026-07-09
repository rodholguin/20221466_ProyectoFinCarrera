"""Sondeo SMV — buscar la FECHA REAL de presentación de cada EEFF (jul-2026).

known_date usa hoy un lag fijo (45d/60d), conservador pero tardío. El ideal es la
fecha de presentación real. El WSDL de fundamentales que ya usamos NO la trae en
las 5 operaciones integradas, pero queda por explorar `obtener_EFData` (grid
paginado) y cualquier otra operación con campos de fecha. Este script:
  1. Lista todas las operaciones y su firma de entrada/salida.
  2. Prueba obtener_EFData e inspecciona sus columnas buscando fechas.
"""
from __future__ import annotations

from zeep import Client
from zeep.helpers import serialize_object

WSDL = "https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx?WSDL"


def list_operations(client: Client) -> None:
    print("=== OPERACIONES Y FIRMAS ===")
    for svc in client.wsdl.services.values():
        for port in svc.ports.values():
            for name, op in port.binding._operations.items():
                try:
                    sig_in = op.input.signature()
                except Exception as e:
                    sig_in = f"(err {e})"
                print(f"\n{name}")
                print(f"  IN : {sig_in}")


def dump_type(client: Client, type_name: str) -> None:
    """Intenta mostrar los elementos de un tipo complejo por nombre."""
    try:
        t = client.get_type(type_name)
        print(f"  tipo {type_name}: {t}")
    except Exception as e:
        print(f"  (no se pudo resolver {type_name}: {e})")


def try_efdata(client: Client) -> None:
    print("\n=== obtener_EFData: intento de llamada ===")
    op = None
    for svc in client.wsdl.services.values():
        for port in svc.ports.values():
            for name, o in port.binding._operations.items():
                if name == "obtener_EFData":
                    op = o
    if op is None:
        print("obtener_EFData no existe")
        return
    print("firma IN:", op.input.signature())

    # Grillas jqGrid suelen aceptar page/rows/sidx/sord/_search + filtros propios.
    # Probar varias combinaciones de kwargs sobre la firma real.
    import itertools
    base_variants = [
        dict(Ejercicio="2023", Periodo="4", Tipo="I"),
        dict(Ejercicio="2023", Periodo="4", Tipo="I", page="1", rows="50",
             sidx="", sord="asc", _search="false"),
        dict(Ejercicio="2023", Periodo="4", Tipo="I", RPJ="B30006"),
    ]
    for kw in base_variants:
        try:
            raw = client.service.obtener_EFData(**kw)
            data = serialize_object(raw)
            print(f"\nkwargs={kw} -> OK, tipo salida {type(data).__name__}")
            # inspeccionar estructura
            sample = data
            if isinstance(data, list) and data:
                sample = data[0]
            print("  muestra:", str(sample)[:600])
            return
        except TypeError as e:
            print(f"kwargs={kw} -> TypeError firma: {e}")
        except Exception as e:
            print(f"kwargs={kw} -> {type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    c = Client(WSDL)
    list_operations(c)
    try_efdata(c)
