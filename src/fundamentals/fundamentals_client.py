"""R4 — Pipeline de indicadores fundamentales trimestrales.

Fuente PRIMARIA (la más segura): web service de Datos Abiertos de la SMV
(regulador estatal, presentación legal obligatoria, datos estructurados).
Fuente SECUNDARIA / validación cruzada: endpoint dataondemand de la BVL, que
es el que ya programó la maestría de Ancajima (POST, devuelve EEFF en Excel).

Estrategia recomendada:
  1. SMV como verdad de registro.
  2. BVL dataondemand para arrancar rápido (reutilizar el repo de la maestría)
     y para contrastar cifras.
  3. Conciliar: si discrepan, mandar SMV.

Notas:
  * El WSDL de la SMV declara operaciones tipo `obtener_GanciaPerdida`
    (Estado de Resultados), situación financiera, flujo de efectivo, etc.
    Hay que inspeccionar el WSDL para los nombres/parámetros exactos: abrir
    en el navegador `<smv_wsdl>` o usar zeep como abajo.
  * Bancos (Credicorp/BCP): taxonomía distinta. Mapear sus cuentas aparte y
    cuidar la moneda (USD a nivel holding).
  * 2005–2007: esperar huecos. Plan de relleno = forward-fill / interpolación
    de 1–2 trimestres, documentado (igual que hizo la maestría).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.universe import FUNDAMENTALS_SCHEMA, Asset


# --------------------------------------------------------------------------
# SMV (PRIMARIA) — web service SOAP de Datos Abiertos
# --------------------------------------------------------------------------
def smv_list_operations(wsdl: str) -> list[str]:
    """Lista las operaciones del web service para descubrir nombres/parámetros.
    Ejecutar una vez en local para mapear el contrato real."""
    from zeep import Client  # pip install zeep

    client = Client(wsdl)
    ops = [op for svc in client.wsdl.services.values()
           for port in svc.ports.values()
           for op in port.binding._operations.keys()]
    return ops


def fetch_smv(asset: Asset, wsdl: str, start: str, end: str) -> pd.DataFrame:
    """Descarga EEFF trimestrales de la SMV y los normaliza a formato largo.

    TODO: ajustar el nombre de operación y los parámetros tras inspeccionar el
    WSDL. Pseudocódigo del patrón esperado:

        client = Client(wsdl)
        for period in trimestres(start, end):
            resp = client.service.obtener_EstadoSituacionFinanciera(
                empresa=asset.smv, anio=period.year, trimestre=period.q,
                tipo="Individual")  # o "Consolidada"
            ... -> filas (account, value, currency) ...
    """
    from zeep import Client

    rows: list[dict] = []
    try:
        client = Client(wsdl)  # noqa: F841
    except Exception as exc:
        print(f"[SMV] {asset.smv}: no se pudo cargar el WSDL ({exc}).")
        return pd.DataFrame(columns=FUNDAMENTALS_SCHEMA)

    # TODO: bucle real por trimestre + operación. Por ahora retorna vacío.
    print(f"[SMV] {asset.smv}: TODO implementar llamadas con operaciones del WSDL.")
    return pd.DataFrame(rows, columns=FUNDAMENTALS_SCHEMA)


# --------------------------------------------------------------------------
# BVL dataondemand (SECUNDARIA) — endpoint usado por la maestría
# --------------------------------------------------------------------------
def fetch_bvl_dataondemand(asset: Asset, url: str, start: str, end: str) -> pd.DataFrame:
    """POST a https://dataondemand.bvl.com.pe/v1/financialstatements/.

    TODO: replicar el payload exacto del repo de la maestría (Dennis Ancajima).
    La maestría reportó bajar Excel por empresa/periodo; aquí se asume que el
    endpoint puede devolver JSON o un binario Excel a parsear con pandas.
    """
    import requests

    payload = {                       # TODO: contrato real (pedir repo maestría)
        "company": asset.bvl,
        "from": start,
        "to": end,
        "period": "Q",
    }
    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[BVL-EEFF] {asset.bvl}: fallo ({exc}).")
        return pd.DataFrame(columns=FUNDAMENTALS_SCHEMA)

    # TODO: parsear resp (JSON o Excel) al formato largo canónico.
    return pd.DataFrame(columns=FUNDAMENTALS_SCHEMA)


# --------------------------------------------------------------------------
# Derivación de ratios para el dataset DRL (P/E, ROE, DY)
# --------------------------------------------------------------------------
def compute_ratios(fundamentals: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    """Calcula P/E, ROE y DY a partir de cuentas crudas + precio.

    Importante:
      * Las cuentas de la SMV vienen EN MILES y en soles o dólares -> homogeneizar.
      * Definir explícitamente numerador/denominador y la convención trailing.
      * P/E necesita precio (de R3) y utilidad por acción (EPS).
    TODO: implementar tras fijar el mapeo de cuentas SMV -> conceptos.
    """
    raise NotImplementedError("Definir mapeo de cuentas SMV y convención de ratios.")


def fetch_fundamentals(asset: Asset, cfg_sources: dict, start: str, end: str,
                       raw_dir: Path) -> pd.DataFrame:
    """Orquesta SMV (primaria) con BVL dataondemand (secundaria)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    fund = cfg_sources["fundamentals"]

    smv = fetch_smv(asset, fund["smv_wsdl"], start, end)
    if not smv.empty:
        smv.to_parquet(raw_dir / f"fund_{asset.bvl}_smv.parquet")
        return smv

    print(f"[fundamentals] {asset.bvl}: SMV vacía -> intentando BVL dataondemand.")
    bvl = fetch_bvl_dataondemand(asset, fund["bvl_dataondemand_url"], start, end)
    if not bvl.empty:
        bvl.to_parquet(raw_dir / f"fund_{asset.bvl}_bvl.parquet")
    return bvl


if __name__ == "__main__":
    from src.universe import Config

    cfg = Config.load()
    # Útil para empezar: descubrir el contrato del WSDL de la SMV.
    print("Operaciones SMV (ejecutar en local con red):")
    try:
        print(smv_list_operations(cfg.sources["fundamentals"]["smv_wsdl"]))
    except Exception as exc:
        print(f"  (no disponible aquí: {exc})")
