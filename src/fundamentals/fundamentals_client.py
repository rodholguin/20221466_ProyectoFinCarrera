"""R4 — Pipeline de indicadores fundamentales trimestrales.

Fuente PRIMARIA: web service SOAP de Datos Abiertos de la SMV.
  WSDL: https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx?WSDL
  Parámetros confirmados: Ejercicio (año str), Periodo (trimestre "1"-"4"), Tipo ("I"/"C")
  IMPORTANTE: el servicio devuelve TODAS las empresas; se filtra por asset.smv_rpj.
  Cobertura confirmada: 2005-2023 sin gaps (probado con Alicorp).

Fuente SECUNDARIA / validación cruzada: endpoint dataondemand de la BVL.
  Estado: endpoints retornan 200 pero null — confirmado inoperativo (junio 2026).
  Se conserva el código como stub por compatibilidad futura.

Estrategia de caché:
  Cada llamada al WSDL devuelve ~8MB (261 empresas).
  Se cachea el resultado crudo por (operación, año, trimestre, tipo) en
  data/raw/smv_cache/ para no re-descargar en llamadas sucesivas de otros activos.

Esquema de datos (FUNDAMENTALS_SCHEMA):
  ticker | period    | known_date | account          | value     | currency | source
  SAGAC1 | 2023-12-31| 2024-02-14 | BG_1D0109        | 486255    | PEN      | smv
  SAGAC1 | 2023-12-31| 2024-02-14 | GP_2D01ST_Q      | 1668693   | PEN      | smv
  SAGAC1 | 2023-12-31| 2024-02-14 | GP_2D01ST_YTD    | 6690567   | PEN      | smv
  SAGAC1 | 2023-12-31| 2024-02-14 | INFO_UtilidadNeta| 72924     | PEN      | smv

  Prefijos de cuenta:
    BG_   = Balance General (Situación Financiera) — Monto1 = saldo al cierre del período
    GP_Q_ = Ganancias y Pérdidas — Monto1 = valor del trimestre
    GP_YTD_ = Ganancias y Pérdidas — Monto3 = acumulado del ejercicio (YTD)
    CF_   = Flujo de Efectivo — Monto1 = acumulado del ejercicio
    INFO_ = Resumen InfoFinanciera (ActivoTotal, PatrimonioTotal, UtilidadNeta, etc.)

  Los montos están en miles de soles o miles de dólares según Moneda.

Notas:
  * Bancos (BCP): taxonomía SBS distinta. Cuentas disponibles pero con nombres distintos.
  * Buenaventura: reporta en USD (Moneda='Dólares').
  * known_date = cierre de trimestre + 45 días (lag conservador de presentación a SMV).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src.universe import FUNDAMENTALS_SCHEMA, Asset

# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------
_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
_FILING_LAG_DAYS = 45   # lag conservador para known_date (presentación a SMV)

# Operaciones SMV y cómo mapear sus campos Monto al formato largo
_SMV_OPS: dict[str, tuple[str, dict[str, str]]] = {
    "obtener_BalanceGeneral": (
        "BG",
        {"Monto1": "current"},          # saldo al cierre del período
    ),
    "obtener_GanciaPerdida": (
        "GP",
        {"Monto1": "Q", "Monto3": "YTD"},  # Q=trimestre, YTD=acumulado ejercicio
    ),
    "obtener_FlujoEfectivo": (
        "CF",
        {"Monto1": "YTD"},              # acumulado del ejercicio
    ),
}

# Cache en memoria por proceso para evitar re-descargas dentro del mismo run
_MEM_CACHE: dict[tuple, list[dict]] = {}


# --------------------------------------------------------------------------
# SMV (PRIMARIA) — web service SOAP de Datos Abiertos
# --------------------------------------------------------------------------
def smv_list_operations(wsdl: str) -> list[str]:
    """Lista las operaciones del WSDL. Útil para discovery."""
    from zeep import Client

    client = Client(wsdl)
    return [
        op
        for svc in client.wsdl.services.values()
        for port in svc.ports.values()
        for op in port.binding._operations.keys()
    ]


def _quarter_periods(start: str, end: str) -> list[tuple[int, int]]:
    """Genera lista de (año, trimestre) entre start y end, ordenada."""
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    result = []
    for year in range(d0.year, d1.year + 1):
        for q in range(1, 5):
            m, day = _QUARTER_END[q]
            period_end = date(year, m, day)
            if period_end < d0 or period_end > d1:
                continue
            result.append((year, q))
    return result


def _period_end(year: int, q: int) -> date:
    m, day = _QUARTER_END[q]
    return date(year, m, day)


def _known_date(year: int, q: int) -> date:
    return _period_end(year, q) + timedelta(days=_FILING_LAG_DAYS)


def _fetch_period_raw(
    client,
    op_name: str,
    year: int,
    q: int,
    tipo: str,
    cache_dir: Path | None,
) -> list[dict]:
    """Descarga (o lee del caché) todos los datos SMV para un período.

    Retorna lista de dicts con todos los registros de todas las empresas.
    """
    from zeep.helpers import serialize_object

    cache_key = (op_name, year, q, tipo)
    if cache_key in _MEM_CACHE:
        return _MEM_CACHE[cache_key]

    if cache_dir is not None:
        disk_path = cache_dir / f"{op_name}_{year}Q{q}_{tipo}.json"
        if disk_path.exists():
            rows = json.loads(disk_path.read_text(encoding="utf-8"))
            _MEM_CACHE[cache_key] = rows
            return rows

    fn = getattr(client.service, op_name)
    raw = fn(Ejercicio=str(year), Periodo=str(q), Tipo=tipo)
    data = serialize_object(raw)
    if isinstance(data, str):
        data = json.loads(data)
    rows: list[dict] = data or []

    _MEM_CACHE[cache_key] = rows
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        disk_path.write_text(
            json.dumps(rows, ensure_ascii=False), encoding="utf-8"
        )
    return rows


def _rows_for_asset(rows: list[dict], asset: Asset) -> list[dict]:
    """Filtra filas por RPJ (exacto) con fallback a NombreEmpresa parcial."""
    if asset.smv_rpj:
        matched = [r for r in rows if r.get("RPJ") == asset.smv_rpj]
        if matched:
            return matched
    # Fallback: coincidencia parcial en NombreEmpresa
    if asset.smv:
        term = asset.smv.lower()
        matched = [r for r in rows if term in (r.get("NombreEmpresa") or "").lower()]
        if matched:
            return matched
    return []


def _normalize_op_rows(
    asset: Asset,
    op_name: str,
    year: int,
    q: int,
    rows: list[dict],
) -> list[dict]:
    """Convierte filas crudas de una operación al formato FUNDAMENTALS_SCHEMA."""
    prefix, monto_map = _SMV_OPS[op_name]
    period_dt = _period_end(year, q)
    known_dt = _known_date(year, q)
    period_str = period_dt.isoformat()
    known_str = known_dt.isoformat()

    currency_map = {"Soles": "PEN", "D lares": "USD", "Dólares": "USD",
                    "Dolares": "USD", "USD": "USD", "PEN": "PEN"}

    out: list[dict] = []
    for row in rows:
        currency = currency_map.get(row.get("Moneda", ""), "PEN")
        cuenta = row.get("Cuenta", "")
        for monto_key, monto_label in monto_map.items():
            val = row.get(monto_key)
            if val is None:
                continue
            if monto_label == "current" or monto_label == "YTD":
                acct = f"{prefix}_{cuenta}"
            else:
                acct = f"{prefix}_{monto_label}_{cuenta}"
            out.append({
                "ticker":     asset.bvl,
                "period":     period_str,
                "known_date": known_str,
                "account":    acct,
                "value":      float(val),
                "currency":   currency,
                "source":     "smv",
            })
    return out


def _normalize_info_rows(
    asset: Asset,
    year: int,
    q: int,
    rows: list[dict],
) -> list[dict]:
    """Convierte filas de obtener_InfoFinanciera al formato FUNDAMENTALS_SCHEMA."""
    period_str = _period_end(year, q).isoformat()
    known_str = _known_date(year, q).isoformat()
    currency_map = {"Soles": "PEN", "D lares": "USD", "Dólares": "USD",
                    "Dolares": "USD", "USD": "USD", "PEN": "PEN"}
    info_fields = ["ActivoTotal", "PatrimonioTotal", "TotalIngreso",
                   "UtilidadNeta", "PasivoTotal"]
    out: list[dict] = []
    for row in rows:
        currency = currency_map.get(row.get("Moneda", ""), "PEN")
        for field in info_fields:
            val = row.get(field)
            if val is None:
                continue
            out.append({
                "ticker":     asset.bvl,
                "period":     period_str,
                "known_date": known_str,
                "account":    f"INFO_{field}",
                "value":      float(val),
                "currency":   currency,
                "source":     "smv",
            })
    return out


def fetch_smv(
    asset: Asset,
    wsdl: str,
    start: str,
    end: str,
    cache_dir: Path | None = None,
    tipo: str = "I",
) -> pd.DataFrame:
    """Descarga EEFF trimestrales de la SMV para un activo.

    Args:
        asset:     activo del universo (necesita smv_rpj o smv para filtrar)
        wsdl:      URL del WSDL de la SMV
        start:     fecha inicio ISO (p.ej. "2005-01-01")
        end:       fecha fin ISO (p.ej. "2025-12-31")
        cache_dir: directorio para caché en disco de respuestas crudas
        tipo:      "I" (Individual) o "C" (Consolidada)

    Returns:
        DataFrame con columnas FUNDAMENTALS_SCHEMA.
        Montos en miles de PEN o USD según la moneda reportada.
    """
    try:
        from zeep import Client
    except ImportError:
        print("[SMV] zeep no instalado. Ejecutar: pip install zeep")
        return pd.DataFrame(columns=FUNDAMENTALS_SCHEMA)

    print(f"[SMV] Conectando a WSDL...")
    try:
        client = Client(wsdl)
    except Exception as exc:
        print(f"[SMV] {asset.bvl}: no se pudo cargar el WSDL ({exc})")
        return pd.DataFrame(columns=FUNDAMENTALS_SCHEMA)

    periods = _quarter_periods(start, end)
    print(f"[SMV] {asset.bvl}: {len(periods)} periodos ({start} -> {end})")

    all_rows: list[dict] = []

    for year, q in periods:
        period_label = f"{year}Q{q}"

        # 1. InfoFinanciera (resumen: ActivoTotal, PatrimonioTotal, etc.)
        try:
            raw = _fetch_period_raw(client, "obtener_InfoFinanciera", year, q, tipo, cache_dir)
            asset_rows = _rows_for_asset(raw, asset)
            if asset_rows:
                all_rows.extend(_normalize_info_rows(asset, year, q, asset_rows))
            else:
                print(f"[SMV] {asset.bvl} {period_label}: no encontrado en InfoFinanciera")
        except Exception as exc:
            print(f"[SMV] {asset.bvl} {period_label} InfoFinanciera: {exc}")

        # 2. BalanceGeneral + GanciaPerdida + FlujoEfectivo
        for op_name in _SMV_OPS:
            try:
                raw = _fetch_period_raw(client, op_name, year, q, tipo, cache_dir)
                asset_rows = _rows_for_asset(raw, asset)
                if asset_rows:
                    all_rows.extend(_normalize_op_rows(asset, op_name, year, q, asset_rows))
            except Exception as exc:
                print(f"[SMV] {asset.bvl} {period_label} {op_name}: {exc}")

    if not all_rows:
        print(f"[SMV] {asset.bvl}: sin datos obtenidos.")
        return pd.DataFrame(columns=FUNDAMENTALS_SCHEMA)

    df = pd.DataFrame(all_rows, columns=FUNDAMENTALS_SCHEMA)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    print(f"[SMV] {asset.bvl}: {len(df)} filas, "
          f"{df['period'].nunique()} periodos, "
          f"cuentas={df['account'].nunique()}")
    return df


# --------------------------------------------------------------------------
# BVL dataondemand (SECUNDARIA) — confirmado inoperativo (junio 2026)
# --------------------------------------------------------------------------
def fetch_bvl_dataondemand(asset: Asset, url: str, start: str, end: str) -> pd.DataFrame:
    """POST a https://dataondemand.bvl.com.pe/v1/financialstatements/.

    Nota: endpoint confirmado inoperativo (retorna 200 null para todos los tickers).
    Se conserva como stub por compatibilidad futura.
    """
    print(f"[BVL-EEFF] {asset.bvl}: endpoint inoperativo (200 null). Sin datos.")
    return pd.DataFrame(columns=FUNDAMENTALS_SCHEMA)


# --------------------------------------------------------------------------
# Derivación de ratios para el dataset DRL (P/E, ROE, DY)
# --------------------------------------------------------------------------
def compute_ratios(
    fundamentals: pd.DataFrame,
    market: pd.DataFrame | None = None,   # reservado para P/E futuro
) -> pd.DataFrame:
    """Calcula ratios fundamentales que no requieren número de acciones.

    Ratios implementados (todos derivables directamente de INFO_* del SMV):
      roe         = UtilidadNeta / PatrimonioTotal
      roa         = UtilidadNeta / ActivoTotal
      net_margin  = UtilidadNeta / TotalIngreso
      debt_equity = PasivoTotal  / PatrimonioTotal
      debt_ratio  = PasivoTotal  / ActivoTotal

    Args:
        fundamentals: output de fetch_smv() en formato largo FUNDAMENTALS_SCHEMA
        market:       no usado actualmente (reservado para P/E cuando se añada
                      el número de acciones por empresa)

    Returns:
        DataFrame ancho con columnas:
        [ticker, period, known_date, currency,
         roe, roa, net_margin, debt_equity, debt_ratio]
        Una fila por (ticker, periodo). Los ratios sin denominador válido son NaN.
    """
    info_accounts = {
        "INFO_UtilidadNeta":   "utilidad_neta",
        "INFO_PatrimonioTotal": "patrimonio",
        "INFO_ActivoTotal":    "activo",
        "INFO_TotalIngreso":   "ingreso",
        "INFO_PasivoTotal":    "pasivo",
    }

    info = fundamentals[fundamentals["account"].isin(info_accounts)].copy()
    if info.empty:
        return pd.DataFrame(columns=[
            "ticker", "period", "known_date", "currency",
            "roe", "roa", "net_margin", "debt_equity", "debt_ratio",
        ])

    info["field"] = info["account"].map(info_accounts)
    wide = info.pivot_table(
        index=["ticker", "period", "known_date", "currency"],
        columns="field",
        values="value",
        aggfunc="first",
    ).reset_index()
    wide.columns.name = None

    # Asegurar que existen todas las columnas (algunas empresas pueden no tenerlas)
    for col in ["utilidad_neta", "patrimonio", "activo", "ingreso", "pasivo"]:
        if col not in wide.columns:
            wide[col] = float("nan")

    def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
        result = num / den.replace(0, float("nan"))
        return result

    wide["roe"]         = _safe_div(wide["utilidad_neta"], wide["patrimonio"])
    wide["roa"]         = _safe_div(wide["utilidad_neta"], wide["activo"])
    wide["net_margin"]  = _safe_div(wide["utilidad_neta"], wide["ingreso"])
    wide["debt_equity"] = _safe_div(wide["pasivo"],        wide["patrimonio"])
    wide["debt_ratio"]  = _safe_div(wide["pasivo"],        wide["activo"])

    cols = ["ticker", "period", "known_date", "currency",
            "roe", "roa", "net_margin", "debt_equity", "debt_ratio"]
    return wide[cols].sort_values(["ticker", "period"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# Orquestador principal
# --------------------------------------------------------------------------
def fetch_fundamentals(
    asset: Asset,
    cfg_sources: dict,
    start: str,
    end: str,
    raw_dir: Path,
) -> pd.DataFrame:
    """Orquesta SMV (primaria) con BVL dataondemand (secundaria, inoperativa)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    fund = cfg_sources["fundamentals"]

    # Directorio de caché de respuestas SMV crudas (compartido entre activos)
    smv_cache = raw_dir / "smv_cache"

    smv = fetch_smv(asset, fund["smv_wsdl"], start, end, cache_dir=smv_cache)
    if not smv.empty:
        out = raw_dir / f"fund_{asset.bvl}_smv.parquet"
        smv.to_parquet(out, index=False)
        print(f"[fundamentals] {asset.bvl}: guardado en {out}")
        return smv

    print(f"[fundamentals] {asset.bvl}: SMV vacía -> BVL dataondemand (inoperativo).")
    return pd.DataFrame(columns=FUNDAMENTALS_SCHEMA)


# --------------------------------------------------------------------------
if __name__ == "__main__":
    from src.universe import Config

    cfg = Config.load()
    fund_cfg = cfg.sources

    for asset in cfg.assets[:1]:   # prueba con primer activo
        print(f"\n{'='*60}")
        print(f"Descargando fundamentales SMV: {asset.name}")
        df = fetch_fundamentals(
            asset, fund_cfg,
            start="2020-01-01", end="2023-12-31",
            raw_dir=Path(cfg.paths["raw"]),
        )
        if not df.empty:
            print(df.head(10).to_string())
            print(f"\nCuentas disponibles: {sorted(df['account'].unique())[:20]}")
