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
  * known_date = FECHA REAL de presentación del EEFF cuando existe (registerDate
    del hecho de importancia en la BVL, ~2018-2025), con fallback al lag fijo
    por trimestre (45d Q1-Q3, 60d Q4) para períodos sin cobertura. Ver
    _load_filing_dates / _known_date y docs/riesgos §3(a).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from src.universe import FUNDAMENTALS_SCHEMA, Asset

# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------
_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
# Lag de known_date por trimestre — usado como FALLBACK cuando no hay fecha real
# de presentación (registerDate BVL; ver más abajo). Cobertura real ~2018-2025,
# así que el fallback aplica sobre todo a 2012-2017. Calibrado empíricamente con
# los plazos regulatorios de la SMV (RSMV 016-2015 art. 5 y 11) y con la
# distribución REAL de lags 2018-2025 (n=109 Q1-Q3):
#   Deadline legal: Q1<=30-abr (~30d), Q2<=31-jul (~31d), Q3<=31-oct (~31d).
#   Lag real: mediana 29d, máximo NORMAL 35d (excluyendo prórrogas de emergencia).
#   Q1-Q3 = 40d: cubre el máximo normal (35) con ~5d de colchón. Un 30d generaría
#     look-ahead en 33% de los trimestres; 40d solo lo tiene en prórrogas de
#     emergencia documentadas (COVID-2020 Res.033-2020-SMV/02; El Niño-2017
#     Res.014-2017-SMV/01), que son excepcionales y caen en/al borde del tramo
#     de fallback -> limitación declarada, no bloqueante.
#   Q4 <= 15-feb local, PERO <= 60 días calendario si el emisor lista también en
#     el extranjero (BUENAVC1/NYSE). Q4 = 60d: es el máximo real observado (BVN
#     Q4-2023 cae exacto en +60d); un +45d ahí filtraría ~14d en BVN.
# Ver docs/riesgos_transversales_datos.txt (Tier 1, punto 3a) para la tabla de
# barrido completa y la justificación numérica.
_FILING_LAG_DAYS = {1: 40, 2: 40, 3: 40, 4: 60}

# --- known_date por FECHA REAL de presentación (BVL Hechos de Importancia) ---
# Fuente preferida cuando existe: el registerDate del hecho "Información Financiera
# Intermedia Individual" en POST /v1/corporate-actions de la BVL. Cobertura real
# ~2018-2025; antes de eso se usa el lag fijo de arriba (fallback, causalmente
# seguro). Validado en los 5 emisores: el lag fijo nunca adelanta al mercado pero
# demora hasta ~5 semanas. Ver scripts/probe_bvl_hechos.py y riesgos §3(a).
_BVL_DOD = "https://dataondemand.bvl.com.pe"
_BVL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": "https://www.bvl.com.pe",
    "Referer": "https://www.bvl.com.pe/",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
}
# Hechos registrados a esta hora o después (hora de Lima) se consideran conocidos
# recién el día siguiente (no operables en el cierre del propio día).
_AFTER_CLOSE_HOUR = 15
# Descartar registerDate absurdamente lejano del cierre (errata/re-presentación
# tardía o parse espurio); esos períodos caen al lag fijo.
_FILING_MAX_LAG_DAYS = 150
_MONTH_ABBR = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
               "jul": 7, "ago": 8, "set": 9, "sep": 9, "oct": 10, "nov": 11,
               "dic": 12}
_QEND_MONTH = {3: 1, 6: 2, 9: 3, 12: 4}
_EEFF_OBS_RE = re.compile(
    r"intermedia individual al\s+(\d{1,2})-([a-zA-Z]{3})-(\d{4})")

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


def _known_date(
    year: int,
    q: int,
    filing_dates: dict[tuple[int, int], date] | None = None,
) -> date:
    """Fecha en que el mercado conoció el EEFF del trimestre.

    Usa la FECHA REAL de presentación (BVL, registerDate) si está disponible en
    `filing_dates`; de lo contrario cae al lag fijo por trimestre (fallback
    causalmente seguro). Ver riesgos §3(a).
    """
    if filing_dates:
        real = filing_dates.get((year, q))
        if real is not None:
            return real
    return _period_end(year, q) + timedelta(days=_FILING_LAG_DAYS[q])


def _bvl_fetch_hechos(
    rpj: str, start: str, end: str, cache_dir: Path | None
) -> list[dict]:
    """Descarga (o lee de caché) los Hechos de Importancia de un emisor desde el
    endpoint POST /v1/corporate-actions de la BVL. Se cachea el crudo por (rpj,
    rango) para reproducibilidad y para no re-descargar en cada activo/run."""
    import requests

    disk_path = None
    if cache_dir is not None:
        disk_path = cache_dir / f"bvl_hechos_{rpj}_{start[:4]}_{end[:4]}.json"
        if disk_path.exists():
            return json.loads(disk_path.read_text(encoding="utf-8"))

    out: list[dict] = []
    page = 1
    while True:
        body = {"rpjCode": rpj, "page": page, "size": 100,
                "search": "", "startDate": start, "endDate": end}
        r = requests.post(_BVL_DOD + "/v1/corporate-actions",
                          headers=_BVL_HEADERS, json=body, timeout=40)
        r.raise_for_status()
        j = r.json()
        out += j.get("content", [])
        if j.get("last") or page >= j.get("totalPages", 1):
            break
        page += 1

    if disk_path is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        disk_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def _load_filing_dates(
    asset: Asset, start: str, end: str, cache_dir: Path | None
) -> dict[tuple[int, int], date]:
    """Mapa (año, trimestre) -> known_date real, a partir del registerDate del
    hecho 'Información Financiera Intermedia Individual' (Tipo=I, lo que consume
    el pipeline). Aplica la regla de cierre (+1 día si se registró >= 15:00),
    toma la PRIMERA divulgación por trimestre y descarta fechas absurdas.
    Devuelve {} si no hay rpj o si el fetch falla -> el pipeline usa lag fijo."""
    rpj = getattr(asset, "smv_rpj", None)
    if not rpj:
        return {}
    try:
        facts = _bvl_fetch_hechos(rpj, start, end, cache_dir)
    except Exception as exc:
        print(f"[BVL-hechos] {asset.bvl}: fetch falló ({exc}); se usará lag fijo.")
        return {}

    out: dict[tuple[int, int], date] = {}
    for f in facts:
        m = _EEFF_OBS_RE.search((f.get("observation") or "").lower())
        if not m:
            continue
        mon = _MONTH_ABBR.get(m.group(2).lower())
        if mon is None or mon not in _QEND_MONTH:
            continue
        year, q = int(m.group(3)), _QEND_MONTH[mon]
        try:
            reg = datetime.strptime(
                str(f["registerDate"]).split(".")[0], "%Y-%m-%d %H:%M:%S")
        except (KeyError, ValueError):
            continue
        lag = (reg.date() - _period_end(year, q)).days
        if lag < 0 or lag > _FILING_MAX_LAG_DAYS:
            continue
        kd = reg.date() + timedelta(days=1) if reg.hour >= _AFTER_CLOSE_HOUR \
            else reg.date()
        if (year, q) not in out or kd < out[(year, q)]:
            out[(year, q)] = kd  # primera divulgación gana
    return out


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
    filing_dates: dict[tuple[int, int], date] | None = None,
) -> list[dict]:
    """Convierte filas crudas de una operación al formato FUNDAMENTALS_SCHEMA."""
    prefix, monto_map = _SMV_OPS[op_name]
    period_dt = _period_end(year, q)
    known_dt = _known_date(year, q, filing_dates)
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
    filing_dates: dict[tuple[int, int], date] | None = None,
) -> list[dict]:
    """Convierte filas de obtener_InfoFinanciera al formato FUNDAMENTALS_SCHEMA."""
    period_str = _period_end(year, q).isoformat()
    known_str = _known_date(year, q, filing_dates).isoformat()
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
    use_filing_dates: bool = True,
) -> pd.DataFrame:
    """Descarga EEFF trimestrales de la SMV para un activo.

    Args:
        asset:     activo del universo (necesita smv_rpj o smv para filtrar)
        wsdl:      URL del WSDL de la SMV
        start:     fecha inicio ISO (p.ej. "2005-01-01")
        end:       fecha fin ISO (p.ej. "2025-12-31")
        cache_dir: directorio para caché en disco de respuestas crudas
        tipo:      "I" (Individual) o "C" (Consolidada)
        use_filing_dates: si True, known_date usa la fecha REAL de presentación
                   (BVL Hechos de Importancia) cuando existe, con fallback al
                   lag fijo. Si False, siempre lag fijo.

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

    # Fechas REALES de presentación (BVL) para known_date; {} => solo lag fijo.
    filing_dates: dict[tuple[int, int], date] = {}
    if use_filing_dates:
        filing_dates = _load_filing_dates(asset, start, end, cache_dir)
        n_real = sum(1 for p in periods if p in filing_dates)
        print(f"[SMV] {asset.bvl}: known_date real (BVL) en {n_real}/{len(periods)} "
              f"periodos; resto usa lag fijo (40/60d).")

    all_rows: list[dict] = []

    for year, q in periods:
        period_label = f"{year}Q{q}"

        # 1. InfoFinanciera (resumen: ActivoTotal, PatrimonioTotal, etc.)
        try:
            raw = _fetch_period_raw(client, "obtener_InfoFinanciera", year, q, tipo, cache_dir)
            asset_rows = _rows_for_asset(raw, asset)
            if asset_rows:
                all_rows.extend(_normalize_info_rows(asset, year, q, asset_rows, filing_dates))
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
                    all_rows.extend(_normalize_op_rows(asset, op_name, year, q, asset_rows, filing_dates))
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
# Acciones en circulación y utilidad TTM (insumos de P/E y EPS)
# --------------------------------------------------------------------------
# Capital emitido y acciones en tesorería en el Balance (Situación Financiera).
# No bancos: 1D0701 (Capital Emitido) / 1D0711 (Acciones Propias en Cartera).
# Banco (BCP, taxonomía SBS): 1F3301 (Capital social) / 1F3314 (Acciones Propias).
# Ver docs/pipeline_extraccion_datos.txt §3.10.2.
_CAPITAL_ACCTS = ("BG_1D0701", "BG_1F3301")
_TREASURY_ACCTS = ("BG_1D0711", "BG_1F3314")
_QMONTH = {"03": 1, "06": 2, "09": 3, "12": 4}


def _detect_net_income_ytd_account(df: pd.DataFrame) -> str | None:
    """Devuelve la cuenta YTD de Utilidad Neta del Estado de Resultados.

    La taxonomía difiere entre empresas (no banco 2D07ST; banco SBS 2F1901), así
    que se detecta emparejando INFO_UtilidadNeta (que es el valor TRIMESTRAL) con
    la cuenta GP_Q_<x> de igual valor, y se devuelve su versión YTD GP_<x>.
    Se usa la serie YTD (Monto3) y NO el trimestral (Monto1): este último tiene
    inconsistencias por reexpresión (p.ej. ALICORC1 2023Q3: Monto1=76,669 vs.
    diferencia de YTD=26,942); el YTD es acumulativo y auto-consistente.
    """
    info = df[df["account"] == "INFO_UtilidadNeta"]
    for period in sorted(df["period"].unique(), reverse=True):
        row = info[info["period"] == period]
        if row.empty:
            continue
        target = float(row["value"].iloc[0])
        tol = max(1.0, abs(target) * 1e-6)
        cand = df[(df["period"] == period)
                  & df["account"].str.startswith("GP_Q_")
                  & (df["value"].sub(target).abs() <= tol)]
        if not cand.empty:
            return "GP_" + cand["account"].iloc[0][len("GP_Q_"):]
    return None


def _ytd_to_quarterly(ytd: pd.Series) -> pd.Series:
    """Convierte una serie YTD (indexada por periodo ISO trimestral) a la utilidad
    TRIMESTRAL aislada, restando el YTD del trimestre anterior DENTRO del mismo
    año (Q1 = YTD(Q1))."""
    ytd = ytd.sort_index()
    # fin de trimestre previo dentro del mismo año, por número de trimestre
    _prev_qend = {2: "03-31", 3: "06-30", 4: "09-30"}
    out = {}
    for period, val in ytd.items():
        q = _QMONTH.get(period[5:7])
        if q is None or pd.isna(val):
            continue
        if q == 1:
            out[period] = val
        else:
            prev = f"{period[:4]}-{_prev_qend[q]}"
            out[period] = (val - ytd[prev]) if prev in ytd.index else float("nan")
    return pd.Series(out).sort_index()


def compute_shares_earnings(fundamentals: pd.DataFrame, asset) -> pd.DataFrame:
    """Deriva, por periodo, las acciones en circulación, la utilidad neta TTM
    (en PEN) y el EPS TTM de un activo, a partir de los EEFF del SMV.

    Acciones en circulación = (Capital Emitido − |Acciones en Cartera|) / nominal,
    en la base del propio periodo. Si el activo trae `shares_outstanding_override`
    (BUENAVC1, capital SMV en USD sin nominal limpio), se usa ese conteo constante.
    Utilidad TTM = suma móvil de 4 trimestres aislados derivados de la serie YTD;
    si la utilidad se reporta en USD (BUENAVC1) se convierte a PEN con el TC BCRP
    a fin de trimestre (src/market/fx). EPS_TTM = UtilidadNeta_TTM / acciones.
    """
    df = fundamentals[fundamentals["ticker"] == asset.bvl]
    periods = sorted(df["period"].unique())
    if not periods:
        return pd.DataFrame(columns=["ticker", "period", "known_date",
                                     "shares_outstanding", "net_income_ttm", "eps_ttm"])
    known = df.drop_duplicates("period").set_index("period")["known_date"]

    # --- acciones en circulación ---
    if asset.shares_outstanding_override:
        shares = pd.Series(float(asset.shares_outstanding_override), index=periods)
    else:
        cap = (df[df["account"].isin(_CAPITAL_ACCTS)]
               .set_index("period")["value"].reindex(periods))
        tes = (df[df["account"].isin(_TREASURY_ACCTS)]
               .set_index("period")["value"].abs().reindex(periods).fillna(0.0))
        shares = (cap - tes) * 1000.0 / float(asset.nominal_value)

    # --- utilidad neta TTM (de la serie YTD, robusta a reexpresiones) ---
    ni_acct = _detect_net_income_ytd_account(df)
    if ni_acct is not None:
        ni_rows = df[df["account"] == ni_acct]
        ytd = ni_rows.set_index("period")["value"]
        cur_all = ni_rows.set_index("period")["currency"]
        q_iso = _ytd_to_quarterly(ytd)                         # miles, moneda del EEFF
        # Conversión a PEN por TRIMESTRE (a su propio TC): solo para reportantes-USD
        # (moneda MODAL = USD, i.e. BUENAVC1) y solo en los trimestres realmente en
        # USD. Así: (i) se convierte cada trimestre al TC de su fecha antes de sumar
        # el TTM (más exacto que un TC único); (ii) se ignora un rótulo "USD"
        # esporádico y erróneo de un reportante-PEN (ALICORC1 2025Q4, §5.4); (iii)
        # los ~7 trimestres PEN pre-2006 de BVN quedan sin convertir.
        modal = cur_all.reindex(q_iso.index).mode()
        if not modal.empty and modal.iloc[0] == "USD":
            from src.market import fx
            rate_q = fx.rate_asof(pd.DatetimeIndex([pd.Timestamp(p) for p in q_iso.index]))
            rate_q = pd.Series(rate_q.to_numpy(), index=q_iso.index)
            is_usd_q = (cur_all.reindex(q_iso.index) == "USD")
            q_iso = q_iso.where(~is_usd_q, q_iso * rate_q)
        ttm = q_iso.rolling(4).sum().reindex(periods)          # PEN, miles
    else:
        ttm = pd.Series(float("nan"), index=periods)

    eps_ttm = (ttm * 1000.0) / shares.replace(0, float("nan"))

    return pd.DataFrame({
        "ticker": asset.bvl,
        "period": periods,
        "known_date": known.reindex(periods).to_numpy(),
        "shares_outstanding": shares.reindex(periods).to_numpy(),
        "net_income_ttm": ttm.reindex(periods).to_numpy(),   # PEN, miles
        "eps_ttm": eps_ttm.reindex(periods).to_numpy(),      # PEN por acción
    })


# --------------------------------------------------------------------------
# Derivación de ratios para el dataset DRL (P/E, ROE, DY)
# --------------------------------------------------------------------------
def compute_ratios(
    fundamentals: pd.DataFrame,
    asset=None,                           # si se da, añade shares/eps para P/E
    market: pd.DataFrame | None = None,   # reservado
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

    # Acciones en circulación + EPS TTM (insumos de P/E), si se conoce el activo.
    # El P/E final se calcula en el panel diario (build_dataset) porque necesita
    # el precio de cada fecha: P/E(t) = close_raw(t) / eps_ttm.
    if asset is not None and (asset.nominal_value or asset.shares_outstanding_override):
        se = compute_shares_earnings(fundamentals, asset)
        if not se.empty:
            wide = wide.merge(se, on=["ticker", "period", "known_date"], how="left")
            cols = cols + ["shares_outstanding", "net_income_ttm", "eps_ttm"]

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
