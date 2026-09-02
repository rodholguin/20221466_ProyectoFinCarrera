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

# --- CORRECCIÓN 2026-09-01: EL LAG GLOBAL SE CALIBRÓ CONTRA UN UNIVERSO QUE YA
# --- NO ES EL VIGENTE, Y PARA InRetail ADELANTA AL MERCADO.
# El barrido de arriba (n=109) se hizo con CREDITC1, BUENAVC1, ALICORC1, SAGAC1
# y CORAREC1. INRETC1 entró DESPUÉS (reemplazó a SAGAC1 en la decisión de
# universo de jul-2026) y su comportamiento de presentación nunca se revalidó.
# Re-medido incluyéndolo, sobre las mismas Q1-Q3:
#     universo viejo (n=109):  lag 40d ->  4/109 ( 3.7%) look-ahead
#     + INRETC1     (n=130):   lag 40d -> 25/130 (19.2%) look-ahead
# 21 de esos 25 son InRetail, repartidos en los 8 años — NO son prórrogas de
# emergencia. Su lag real es 43-47d en Q1-Q3 (mediana 45) y 57-61d en Q4: el
# fallback de 40/60 le mete ~5-7 días de look-ahead TODOS los trimestres del
# tramo 2012-2017. Es una regresión por cambio de configuración: cambió el
# universo y la constante calibrada no se re-verificó.
#
# EL ARREGLO: el lag de fallback se calibra POR ACTIVO con la distribución real
# de ese mismo emisor (`_calibra_lag`), y solo se usa el global cuando el activo
# no tiene observaciones suficientes.
# DIRECCIÓN SEGURA: alargar el lag solo RETRASA (diluye); acortarlo ADELANTA
# (contamina el backtest). Ante la duda se alarga. Por eso el calibrado toma el
# MÁXIMO normal observado más un colchón, y nunca baja del global.
_FILING_LAG_COLCHON = 5      # mismo criterio con que se eligió 40 sobre 35
_FILING_LAG_MIN_OBS = 4      # menos observaciones que esto -> no se calibra
# Trimestres con prórroga de emergencia DOCUMENTADA: no representan el
# comportamiento normal del emisor y sesgarían el calibrado hacia arriba.
#   COVID-2020: Res. 033-2020-SMV/02 (Q1) y 046-2020-SMV/02 (Q2).
_FILING_PRORROGAS = {(2020, 1), (2020, 2)}


def _calibra_lag(filing_dates: dict[tuple[int, int], date] | None) -> dict[int, int]:
    """Lag de fallback POR ACTIVO, a partir de sus propias presentaciones reales.

    Devuelve {trimestre: días}. Para cada grupo de trimestres (Q1-Q3 comparten
    deadline legal; Q4 es distinto) toma el MÁXIMO lag normal observado más un
    colchón, y nunca devuelve menos que el global — así el cambio solo puede
    retrasar, nunca adelantar, respecto del comportamiento actual.

    Con menos de `_FILING_LAG_MIN_OBS` observaciones no calibra: un máximo sobre
    2-3 puntos no es una cota, es ruido.
    """
    if not filing_dates:
        return dict(_FILING_LAG_DAYS)
    lags: dict[int, list[int]] = {}
    for (year, q), fecha in filing_dates.items():
        if (year, q) in _FILING_PRORROGAS:
            continue
        lags.setdefault(q, []).append((fecha - _period_end(year, q)).days)
    out = dict(_FILING_LAG_DAYS)
    for grupo in ((1, 2, 3), (4,)):
        obs = [d for q in grupo for d in lags.get(q, [])]
        if len(obs) < _FILING_LAG_MIN_OBS:
            continue
        propuesto = max(obs) + _FILING_LAG_COLCHON
        for q in grupo:
            out[q] = max(_FILING_LAG_DAYS[q], propuesto)
    return out

# --- known_date por FECHA REAL de presentación (BVL Hechos de Importancia) ---
# Fuente preferida cuando existe: el registerDate del hecho "Información Financiera
# Intermedia <Individual|Consolidada>" en POST /v1/corporate-actions de la BVL.
# Cobertura real ~2018-2025; antes de eso se usa el lag fijo de arriba (fallback,
# causalmente seguro). Validado en los 5 emisores: el lag fijo nunca adelanta al
# mercado pero demora hasta ~5 semanas. Ver scripts/probe_bvl_hechos.py y riesgos §3(a).
# CLAVE: el hecho debe corresponder al MISMO tipo de EEFF que se consume (`tipo`).
# La consolidada NO siempre se presenta el mismo día que la individual: medido
# jul-2026, en INRETC1 (el único activo con smv_tipo="C") la consolidada llega
# 9-19 días DESPUÉS (mediana 14) en 30/30 trimestres, mientras que en ALICORC1 y
# CREDITC1 el gap es 0/30 y 0/26 días. Fechar cifras consolidadas con el hecho
# "Individual" inyectaría ~2 semanas de look-ahead por trimestre.
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
_EEFF_OBS_RE = {   # tipo de EEFF consumido -> patrón del hecho que lo divulga
    "I": re.compile(r"intermedia individual al\s+(\d{1,2})-([a-zA-Z]{3})-(\d{4})"),
    "C": re.compile(r"intermedia consolidada al\s+(\d{1,2})-([a-zA-Z]{3})-(\d{4})"),
}

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
    lags: dict[int, int] | None = None,
) -> tuple[date, bool]:
    """Fecha en que el mercado conoció el EEFF del trimestre, y si es REAL.

    Devuelve `(fecha, es_real)`:
      - `es_real=True`  -> FECHA REAL de presentación (registerDate del hecho de
        importancia en la BVL). Cobertura ~2018-2025.
      - `es_real=False` -> FALLBACK por lag, calibrado para ESTE activo con
        `_calibra_lag` (o el global si no hubo observaciones suficientes).

    POR QUÉ SE DEVUELVE LA BANDERA Y NO SOLO LA FECHA. La cobertura de fecha real
    NO es aleatoria: es 0% hasta 2017 y ~96% desde 2019, o sea que la variable
    significa cosas distintas en train (32.5% real) y en test (85.2% real). Sin
    la bandera ese cambio de régimen es invisible para el panel y para la
    ablación de R8. Ver riesgos §3(a) y D20.
    """
    if filing_dates:
        real = filing_dates.get((year, q))
        if real is not None:
            return real, True
    lag = (lags or _FILING_LAG_DAYS)[q]
    return _period_end(year, q) + timedelta(days=lag), False


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
    asset: Asset, start: str, end: str, cache_dir: Path | None, tipo: str = "I"
) -> dict[tuple[int, int], date]:
    """Mapa (año, trimestre) -> known_date real, a partir del registerDate del
    hecho 'Información Financiera Intermedia <Individual|Consolidada>' que
    corresponde al `tipo` de EEFF que el pipeline realmente consume (ver nota de
    los patrones _EEFF_OBS_RE: en INRETC1 la consolidada se divulga ~2 semanas
    después de la individual, así que cruzar los tipos sería look-ahead).
    Aplica la regla de cierre (+1 día si se registró >= 15:00), toma la PRIMERA
    divulgación por trimestre y descarta fechas absurdas.
    Devuelve {} si no hay rpj o si el fetch falla -> el pipeline usa lag fijo."""
    rpj = getattr(asset, "smv_rpj", None)
    if not rpj:
        return {}
    pattern = _EEFF_OBS_RE.get(tipo, _EEFF_OBS_RE["I"])
    try:
        facts = _bvl_fetch_hechos(rpj, start, end, cache_dir)
    except Exception as exc:
        print(f"[BVL-hechos] {asset.bvl}: fetch falló ({exc}); se usará lag fijo.")
        return {}

    out: dict[tuple[int, int], date] = {}
    for f in facts:
        m = pattern.search((f.get("observation") or "").lower())
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
    lags: dict[int, int] | None = None,
) -> list[dict]:
    """Convierte filas crudas de una operación al formato FUNDAMENTALS_SCHEMA."""
    prefix, monto_map = _SMV_OPS[op_name]
    period_dt = _period_end(year, q)
    known_dt, known_real = _known_date(year, q, filing_dates, lags)
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
                "known_date_real": int(known_real),
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
    lags: dict[int, int] | None = None,
) -> list[dict]:
    """Convierte filas de obtener_InfoFinanciera al formato FUNDAMENTALS_SCHEMA."""
    period_str = _period_end(year, q).isoformat()
    known_dt, known_real = _known_date(year, q, filing_dates, lags)
    known_str = known_dt.isoformat()
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
                "known_date_real": int(known_real),
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
    tipo: str | None = None,
    use_filing_dates: bool = True,
) -> pd.DataFrame:
    """Descarga EEFF trimestrales de la SMV para un activo.

    Args:
        asset:     activo del universo (necesita smv_rpj o smv para filtrar)
        wsdl:      URL del WSDL de la SMV
        start:     fecha inicio ISO (p.ej. "2005-01-01")
        end:       fecha fin ISO (p.ej. "2025-12-31")
        cache_dir: directorio para caché en disco de respuestas crudas
        tipo:      "I" (Individual) o "C" (Consolidada). Si es None se toma de
                   `asset.smv_tipo` (config.yaml) y, en su defecto, "I". El
                   único activo del universo que EXIGE "C" es INRETC1: InRetail
                   es un holding y su EEFF individual reporta pérdida (el
                   negocio está en las subsidiarias), lo que dejaría el P/E en
                   NaN. La caché de disco está indexada por tipo
                   (op_year_Q_tipo.json), así que "I" y "C" coexisten.
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

    tipo = tipo or asset.smv_tipo or "I"
    periods = _quarter_periods(start, end)
    print(f"[SMV] {asset.bvl}: {len(periods)} periodos ({start} -> {end}), "
          f"tipo={tipo} ({'Consolidado' if tipo == 'C' else 'Individual'})")

    # Fechas REALES de presentación (BVL) para known_date; {} => solo lag fijo.
    filing_dates: dict[tuple[int, int], date] = {}
    if use_filing_dates:
        # El hecho de importancia consultado debe ser del MISMO tipo (I/C) que los
        # EEFF que se descargan; ver _load_filing_dates.
        filing_dates = _load_filing_dates(asset, start, end, cache_dir, tipo=tipo)
        n_real = sum(1 for p in periods if p in filing_dates)
        print(f"[SMV] {asset.bvl}: known_date real (BVL, hecho tipo {tipo}) en "
              f"{n_real}/{len(periods)} periodos.")

    # Lag de fallback CALIBRADO CON ESTE EMISOR (2026-09-01). El global 40/60 se
    # calibró contra un universo que ya no es el vigente y le mete ~5-7d de
    # look-ahead a InRetail en todo el tramo sin fecha real. Ver _calibra_lag.
    lags = _calibra_lag(filing_dates)
    if lags != _FILING_LAG_DAYS:
        print(f"[SMV] {asset.bvl}: lag de fallback CALIBRADO "
              f"Q1-Q3={lags[1]}d Q4={lags[4]}d (global {_FILING_LAG_DAYS[1]}/"
              f"{_FILING_LAG_DAYS[4]}) — este emisor presenta más tarde que la media.")
    else:
        print(f"[SMV] {asset.bvl}: lag de fallback global "
              f"Q1-Q3={lags[1]}d Q4={lags[4]}d.")

    all_rows: list[dict] = []

    for year, q in periods:
        period_label = f"{year}Q{q}"

        # 1. InfoFinanciera (resumen: ActivoTotal, PatrimonioTotal, etc.)
        try:
            raw = _fetch_period_raw(client, "obtener_InfoFinanciera", year, q, tipo, cache_dir)
            asset_rows = _rows_for_asset(raw, asset)
            if asset_rows:
                all_rows.extend(_normalize_info_rows(asset, year, q, asset_rows, filing_dates, lags))
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
                    all_rows.extend(_normalize_op_rows(asset, op_name, year, q, asset_rows, filing_dates, lags))
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

# Conteo oficial de acciones LISTADAS (Informe Bursátil Mensual de la BVL). Es la
# fecha correcta de reconocimiento: mientras las acciones nuevas no estén listadas
# no están en el mercado. Ver docs/ejecutabilidad_y_costos_OE1.txt §4.5(b) y §8.
# La ruta debe coincidir con bvl_infmen._CACHE (lo genera scripts/gen_bvl_mensual.py);
# no se importa arriba porque src.market.__init__ arrastra market_client entero.
_BVL_MENSUAL_CACHE = Path("data/interim/bvl_mensual.parquet")
_BVL_MENSUAL_DF: pd.DataFrame | None = None
_BVL_MENSUAL_TRIED = False


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


def _shares_from_schedule(schedule: tuple[tuple[str, int], ...],
                          periods: list[str], ticker: str = "") -> pd.Series:
    """Conteo de acciones por periodo a partir de un calendario por TRAMOS.

    `schedule` = ((fecha_desde ISO, conteo), ...): cada entrada rige desde ese
    periodo (inclusive) hasta el inicio del tramo siguiente — una función
    escalonada, no una interpolación (un follow-on o una escisión cambia el
    conteo de golpe en una fecha, no gradualmente).

    Periodos ANTERIORES al primer tramo toman el conteo más antiguo declarado
    (misma convención que un override constante) y se avisa por consola.
    """
    sched = sorted((str(desde), float(conteo)) for desde, conteo in schedule)
    inicios = pd.DatetimeIndex([pd.Timestamp(d) for d, _ in sched])
    conteos = [c for _, c in sched]

    pos = inicios.searchsorted(pd.DatetimeIndex(periods), side="right") - 1
    previos = int((pos < 0).sum())
    if previos:
        print(f"[shares] {ticker}: {previos} periodo(s) anteriores al primer tramo "
              f"({sched[0][0]}) -> se usa el conteo más antiguo ({conteos[0]:,.0f}).")
    valores = [conteos[max(p, 0)] for p in pos]
    return pd.Series(valores, index=periods, dtype=float)


def _bvl_mensual() -> pd.DataFrame | None:
    """Panel mensual oficial de la BVL (caché en disco), o None si no está.

    Se lee SOLO del parquet ya generado (scripts/gen_bvl_mensual.py): construirlo
    aquí dispararía la descarga de ~174 PDF en medio del pipeline de R4.
    """
    global _BVL_MENSUAL_DF, _BVL_MENSUAL_TRIED
    if _BVL_MENSUAL_TRIED:
        return _BVL_MENSUAL_DF
    _BVL_MENSUAL_TRIED = True
    if not _BVL_MENSUAL_CACHE.exists():
        print(f"[shares] {_BVL_MENSUAL_CACHE} no existe -> se usa el capital del "
              f"balance SMV (sin capa oficial de la BVL). "
              f"Generarlo con scripts/gen_bvl_mensual.py.")
        _BVL_MENSUAL_DF = None
    else:
        from src.market import bvl_infmen
        _BVL_MENSUAL_DF = bvl_infmen.load_mensual(cache=_BVL_MENSUAL_CACHE)
    return _BVL_MENSUAL_DF


def _shares_listed_bvl(periods: list[str], ticker: str) -> pd.Series:
    """Acciones EMITIDAS Y LISTADAS según la BVL, alineadas al mes de cierre de
    cada periodo trimestral. NaN donde no hay dato oficial (antes de 2012-01,
    después del último informe, o activo ausente del panel).

    El conteo es una función ESCALONADA, así que el hueco de 2016-03 (tabla
    rasterizada, ver §4.4 del doc de ejecutabilidad) se rellena con ffill sobre el
    calendario mensual completo: es exacto, no una interpolación.
    """
    df = _bvl_mensual()
    if df is None:
        return pd.Series(float("nan"), index=periods, dtype=float)

    serie = (df[df["nemonico"] == ticker]
             .dropna(subset=["acciones_circulacion"])
             .drop_duplicates("periodo", keep="last")
             .set_index("periodo")["acciones_circulacion"]
             .sort_index())
    if serie.empty:
        print(f"[shares] {ticker}: sin filas en el informe bursátil mensual "
              f"-> se usa el capital del balance SMV.")
        return pd.Series(float("nan"), index=periods, dtype=float)

    # ffill SOLO dentro del rango cubierto por la fuente: fuera de él no hay
    # información y debe caer al cálculo del balance, no arrastrar el último valor.
    rango = pd.period_range(serie.index.min(), serie.index.max(), freq="M")
    serie = serie.reindex(rango).ffill()

    meses = pd.PeriodIndex([pd.Period(p, freq="M") for p in periods])
    return pd.Series(serie.reindex(meses).to_numpy(), index=periods, dtype=float)


def compute_shares_earnings(fundamentals: pd.DataFrame, asset) -> pd.DataFrame:
    """Deriva, por periodo, las acciones en circulación, la utilidad neta TTM
    (en PEN) y el EPS TTM de un activo, a partir de los EEFF del SMV.

    Acciones en circulación, por orden de precedencia:
      1. `shares_outstanding_schedule` — calendario por TRAMOS, cuando el conteo
         cambió y no se puede derivar del capital/nominal (INRETC1: sin valor
         nominal por ser holding panameño, y un follow-on exacto en 2022-Q2).
      2. `shares_outstanding_override` — conteo constante: capital SMV en USD sin
         nominal limpio (BUENAVC1, ancla SEC) o acción de inversión cuyo capital no
         divide por nominal (MINSURI1, override = total económico).
      3. CONTEO HÍBRIDO — el caso general (resto del universo):
             acciones = emitidas y LISTADAS (BVL, informe bursátil mensual)
                        − |Acciones en Cartera| (tesorería SMV) / nominal
         Cada fuente aporta lo que hace bien: la BVL da la FECHA de reconocimiento
         correcta (el capital del balance se adelanta hasta 3 trimestres al listado
         — CREDITC1 capitaliza utilidades cada año, sesgo de +2% a +26% en 15 de 54
         trimestres) y el SMV da el AJUSTE correcto (la BVL cuenta acciones
         emitidas sin descontar la tesorería — ALICORC1 2022). Sin dato oficial
         (periodos previos a 2012) se cae a (Capital Emitido − tesorería)/nominal.
         Ver docs/ejecutabilidad_y_costos_OE1.txt §4.5 y §8.
    Utilidad TTM = suma móvil de 4 trimestres aislados derivados de la serie YTD;
    si la utilidad se reporta en USD (BUENAVC1, MINSURI1) se convierte a PEN con el
    TC BCRP a fin de trimestre (src/market/fx). EPS_TTM = UtilidadNeta_TTM / acciones.
    """
    df = fundamentals[fundamentals["ticker"] == asset.bvl]
    periods = sorted(df["period"].unique())
    if not periods:
        return pd.DataFrame(columns=["ticker", "period", "known_date",
                                     "known_date_real", "shares_outstanding",
                                     "net_income_ttm", "eps_ttm"])
    porper = df.drop_duplicates("period").set_index("period")
    known = porper["known_date"]
    known_real = (porper["known_date_real"] if "known_date_real" in porper
                  else pd.Series(0, index=porper.index))

    # --- acciones en circulación ---
    # Precedencia: calendario por tramos > override constante > capital/nominal.
    if getattr(asset, "shares_outstanding_schedule", None):
        shares = _shares_from_schedule(
            asset.shares_outstanding_schedule, periods, asset.bvl)
    elif asset.shares_outstanding_override:
        shares = pd.Series(float(asset.shares_outstanding_override), index=periods)
    else:
        cap = (df[df["account"].isin(_CAPITAL_ACCTS)]
               .set_index("period")["value"].reindex(periods))
        tes = (df[df["account"].isin(_TREASURY_ACCTS)]
               .set_index("period")["value"].abs().reindex(periods).fillna(0.0))
        nominal = float(asset.nominal_value)
        # CONTEO HÍBRIDO: emitidas y LISTADAS (BVL, fecha correcta de
        # reconocimiento) − en cartera (tesorería SMV, ajuste correcto). El
        # capital del balance se adelanta hasta 3 trimestres al listado y la BVL
        # no descuenta la tesorería, así que cada fuente aporta lo suyo.
        emitidas = _shares_listed_bvl(periods, asset.bvl)
        tes_acc = tes * 1000.0 / nominal
        del_balance = (cap - tes) * 1000.0 / nominal
        shares = (emitidas - tes_acc).combine_first(del_balance)
        n_fallback = int(emitidas.isna().sum())
        if n_fallback:
            print(f"[shares] {asset.bvl}: {n_fallback}/{len(periods)} periodo(s) "
                  f"sin conteo oficial de la BVL -> capital del balance SMV.")

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
        "known_date_real": known_real.reindex(periods).fillna(0).astype(int).to_numpy(),
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
        [ticker, period, known_date, known_date_real, currency,
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
            "ticker", "period", "known_date", "known_date_real", "currency",
            "roe", "roa", "net_margin", "debt_equity", "debt_ratio",
        ])

    info["field"] = info["account"].map(info_accounts)
    wide = info.pivot_table(
        # D20:  viaja en la CLAVE del pivot para que llegue al
        # panel sin un merge extra. Es constante dentro de (ticker, period).
        index=["ticker", "period", "known_date", "known_date_real", "currency"],
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

    cols = ["ticker", "period", "known_date", "known_date_real", "currency",
            "roe", "roa", "net_margin", "debt_equity", "debt_ratio"]

    # Acciones en circulación + EPS TTM (insumos de P/E), si se conoce el activo.
    # El P/E final se calcula en el panel diario (build_dataset) porque necesita
    # el precio de cada fecha: P/E(t) = close_raw(t) / eps_ttm.
    if asset is not None and (asset.nominal_value or asset.shares_outstanding_override
                              or getattr(asset, "shares_outstanding_schedule", None)):
        se = compute_shares_earnings(fundamentals, asset)
        if not se.empty:
            wide = wide.merge(se, on=["ticker", "period", "known_date", "known_date_real"],
                              how="left")
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
    tipo: str | None = None,
) -> pd.DataFrame:
    """Orquesta SMV (primaria) con BVL dataondemand (secundaria, inoperativa).

    `tipo`: "I"/"C" para forzar Individual/Consolidado; por defecto (None) se usa
    el de config.yaml por activo (`asset.smv_tipo`, "C" en INRETC1) -- ver fetch_smv.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    fund = cfg_sources["fundamentals"]

    # Directorio de caché de respuestas SMV crudas (compartido entre activos)
    smv_cache = raw_dir / "smv_cache"

    smv = fetch_smv(asset, fund["smv_wsdl"], start, end, cache_dir=smv_cache, tipo=tipo)
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
