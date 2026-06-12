"""Sonda 3: extrae datos reales del SMV para las 5 empresas del universo.

Confirma:
  - nombres exactos de las empresas en el registro SMV
  - cuentas disponibles por estado financiero
  - significado de Monto1/Monto2/Monto3/Monto4
  - cobertura histórica (2005-2025)
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

SMV_WSDL = "https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx?WSDL"
SEP = "=" * 70

UNIVERSE_SMV = [
    "Banco de Credito del Peru S.A.",
    "Compañia de Minas Buenaventura S.A.A.",
    "Alicorp S.A.A.",
    "Saga Falabella S.A.",
    "Corporacion Aceros Arequipa S.A.",
]

# Nombres alternativos por si hay variante ortográfica
SEARCH_TERMS = [
    ["credito", "banco credito", "bcp"],
    ["buenaventura"],
    ["alicorp"],
    ["saga", "falabella"],
    ["aceros arequipa", "corarec"],
]


def load_client():
    from zeep import Client
    return Client(SMV_WSDL)


def call_op(client, op_name, ejercicio, periodo, tipo):
    """Llama a una operación SMV y parsea el resultado JSON."""
    from zeep.helpers import serialize_object
    fn = getattr(client.service, op_name)
    raw = fn(Ejercicio=str(ejercicio), Periodo=str(periodo), Tipo=tipo)
    data = serialize_object(raw)
    if isinstance(data, str):
        data = json.loads(data)
    return data or []


def filter_empresa(rows: list, search_terms: list[str]) -> list:
    """Filtra filas por nombre de empresa (búsqueda parcial, insensible a mayúsculas)."""
    result = []
    for row in rows:
        nombre = (row.get("NombreEmpresa") or "").lower()
        if any(t.lower() in nombre for t in search_terms):
            result.append(row)
    return result


# =============================================================================
# A: Verificar nombres exactos de nuestras empresas en SMV
# =============================================================================
def section_a_nombres():
    print(SEP)
    print("SECCION A: Nombres exactos de empresas en SMV (obtener_InfoFinanciera)")
    print(SEP)
    client = load_client()
    rows = call_op(client, "obtener_InfoFinanciera", 2023, 4, "I")
    print(f"  Total empresas en SMV Q4-2023: {len(rows)}")
    print()

    for i, (smv_name, terms) in enumerate(zip(UNIVERSE_SMV, SEARCH_TERMS)):
        matches = filter_empresa(rows, terms)
        print(f"  Buscando '{smv_name}' -> {len(matches)} coincidencias:")
        for m in matches:
            print(f"    RPJ={m.get('RPJ')}  NombreEmpresa={m.get('NombreEmpresa')!r}")
            print(f"      ActivoTotal={m.get('ActivoTotal')}  UtilidadNeta={m.get('UtilidadNeta')}")
            print(f"      Moneda={m.get('Moneda')}  Trimestre={m.get('Trimestre')}")
        print()

    # Guardar todos los nombres para inspección
    nombres = sorted(set(r.get("NombreEmpresa", "") for r in rows))
    out = Path("data/interim/smv_empresas_2023q4.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(nombres), encoding="utf-8")
    print(f"  Lista completa guardada en {out} ({len(nombres)} empresas)")


# =============================================================================
# B: Inspeccionar cuentas de Alicorp (BalanceGeneral + GanciaPerdida)
# =============================================================================
def section_b_cuentas():
    print()
    print(SEP)
    print("SECCION B: Cuentas de Alicorp S.A.A. — Q4-2023")
    print(SEP)
    client = load_client()

    for op_name, terms in [
        ("obtener_BalanceGeneral",    ["alicorp"]),
        ("obtener_GanciaPerdida",     ["alicorp"]),
        ("obtener_FlujoEfectivo",     ["alicorp"]),
        ("obtener_ResultadosIntegrales", ["alicorp"]),
    ]:
        rows = call_op(client, op_name, 2023, 4, "I")
        matches = filter_empresa(rows, terms)
        print(f"\n  {op_name}: {len(matches)} filas para Alicorp")
        if matches:
            # Mostrar primeras 10
            for r in matches[:10]:
                montos = {k: v for k, v in r.items() if k.startswith("Monto")}
                print(f"    Cuenta={r.get('Cuenta')}  Desc={r.get('DescripcionCuenta')!r}")
                print(f"      {montos}")
            if len(matches) > 10:
                print(f"    ... [{len(matches)-10} cuentas más]")
            # Guardar como JSON
            out = Path(f"data/interim/smv_alicorp_{op_name}_2023q4.json")
            out.write_text(json.dumps(matches, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"    -> Guardado en {out}")
        else:
            print("    [sin resultados -- verificar nombre empresa]")


# =============================================================================
# C: Cobertura histórica (¿desde qué año tiene datos?)
# =============================================================================
def section_c_cobertura():
    print()
    print(SEP)
    print("SECCION C: Cobertura historica para Alicorp (obtener_InfoFinanciera)")
    print(SEP)
    client = load_client()

    years = list(range(2023, 2004, -1))  # 2023 hacia atras
    found_years = []

    for year in years:
        for periodo in ["4", "3", "2", "1"]:  # probar todos los trimestres
            try:
                rows = call_op(client, "obtener_InfoFinanciera", year, periodo, "I")
                matches = filter_empresa(rows, ["alicorp"])
                if matches:
                    found_years.append((year, periodo, matches[0].get("UtilidadNeta")))
                    print(f"  {year} Q{periodo}: OK  UtilidadNeta={matches[0].get('UtilidadNeta')}")
                    break  # solo necesitamos confirmar que existe ese año
                else:
                    print(f"  {year} Q{periodo}: datos SMV presentes pero Alicorp no encontrada")
                    break
            except Exception as e:
                print(f"  {year} Q{periodo}: ERROR {str(e)[:80]}")
                break

    print(f"\n  Cobertura confirmada: {[y for y,_,_ in found_years]}")
    if found_years:
        min_y = min(y for y, _, _ in found_years)
        max_y = max(y for y, _, _ in found_years)
        print(f"  Rango: {min_y} - {max_y}")


# =============================================================================
# D: InfoFinanciera de las 5 empresas en ultimo trimestre disponible
# =============================================================================
def section_d_cinco_empresas():
    print()
    print(SEP)
    print("SECCION D: InfoFinanciera de las 5 empresas — Q4-2023 Individual")
    print(SEP)
    client = load_client()
    rows = call_op(client, "obtener_InfoFinanciera", 2023, 4, "I")

    for smv_name, terms in zip(UNIVERSE_SMV, SEARCH_TERMS):
        matches = filter_empresa(rows, terms)
        print(f"\n  {smv_name}:")
        if matches:
            for m in matches[:3]:  # por si hay varias entidades
                print(f"    RPJ={m.get('RPJ')}  NombreEmpresa={m.get('NombreEmpresa')!r}")
                print(f"    ActivoTotal={m.get('ActivoTotal'):,}  PatrimonioTotal={m.get('PatrimonioTotal'):,}")
                print(f"    TotalIngreso={m.get('TotalIngreso'):,}  UtilidadNeta={m.get('UtilidadNeta'):,}")
                print(f"    PasivoTotal={m.get('PasivoTotal'):,}  Moneda={m.get('Moneda')}")
        else:
            print(f"    [NO ENCONTRADA con terminos {terms}]")
            # Buscar candidatos aproximados
            candidatos = [r for r in rows if any(
                t in (r.get("NombreEmpresa") or "").lower()
                for t in [smv_name.lower()[:6]]
            )]
            for c in candidatos[:3]:
                print(f"    Candidato: {c.get('NombreEmpresa')!r}")

    # También probar con Tipo="C" (Consolidada) para BCP/Credicorp
    print("\n  BCP con Tipo='C' (Consolidada):")
    rows_c = call_op(client, "obtener_InfoFinanciera", 2023, 4, "C")
    matches_bcp = filter_empresa(rows_c, ["credito", "bcp"])
    for m in matches_bcp[:3]:
        print(f"    RPJ={m.get('RPJ')}  {m.get('NombreEmpresa')!r}")
        print(f"    ActivoTotal={m.get('ActivoTotal'):,}  UtilidadNeta={m.get('UtilidadNeta'):,}  Moneda={m.get('Moneda')}")


# =============================================================================
if __name__ == "__main__":
    secs = set(sys.argv[1:]) or {"a", "b", "c", "d"}
    if "a" in secs: section_a_nombres()
    if "b" in secs: section_b_cuentas()
    if "c" in secs: section_c_cobertura()
    if "d" in secs: section_d_cinco_empresas()
    print("\n" + SEP)
    print("FIN")
