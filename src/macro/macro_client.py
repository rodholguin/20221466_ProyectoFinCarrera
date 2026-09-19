"""Features macroeconómicos globales del BCRP para el panel unificado (R6).

Perú es una economía pequeña, abierta y exportadora de minerales: los factores
macro que mueven la BVL no son solo las tasas. Este módulo añade, como columnas
GLOBALES (mismo valor para todos los activos en una fecha), seis series duras del
BCRP, elegidas y respaldadas en docs/fundamento_macro_riesgo_politico.txt:

  feature            código BCRP   frecuencia   qué capta
  macro_tc_usdpen    PD04640PD     diaria       dolarización (via src.market.fx)
  macro_cobre        PD04701XD     diaria       driver macro maestro del Perú
  macro_embi         PD04709XD     diaria       riesgo país / político doméstico
  macro_tasa_ref     PD04722MM     mensual      política monetaria (banca, crédito)
  macro_inflacion    PN01271PM     mensual      IPC Lima (var% mensual)

Códigos y cobertura 2012-2025 VALIDADOS contra el API (scripts/probe_bcrp_macro.py).

Diseño (coherente con R6 = crudo, OE1 = transforma, ver hallazgos_integracion_R6):
  - Se guardan NIVELES CRUDOS. La transformación (retorno log en precios; nivel +
    cambio en tasa/EMBI) se aplica en OE1 al construir la observación.
  - Point-in-time: las diarias se alinean con `asof` (último dato <= fecha). Las
    MENSUALES usan known_date = fecha de publicación para no adelantar información:
    IPC del mes M se publica ~el 1 de M+1 -> efectivo el 1er día de M+1; la tasa de
    referencia del mes M se conoce dentro de M -> efectivo al fin de mes M (sin
    look-ahead: a fin de mes ya ocurrieron todas las reuniones del mes).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

_BCRP_URL = ("https://estadisticas.bcrp.gob.pe/estadisticas/series/api/"
             "{code}/json/{start}/{end}")
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
_CACHE = Path("data/interim/macro_bcrp.parquet")

# Abreviaturas de mes del BCRP (español). OJO: setiembre = "Set".
_MONTHS = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
           "Jul": 7, "Ago": 8, "Set": 9, "Sep": 9,  # diario usa "Set", mensual "Sep"
           "Oct": 10, "Nov": 11, "Dic": 12}

# code, frecuencia ('D' diaria / 'M' mensual)
#
# ORO ELIMINADO EL 2026-09-01 — aplica el veredicto (1) de
# docs/fundamento_macro_riesgo_politico.txt §4.4, DECIDIDO en ago-2026 y que
# nunca se había implementado: la columna seguía entrando al panel.
# Perdió las dos patas a la vez: su activo justificante (BUENAVC1, minera de oro)
# salió del universo en jul-2026, y no tiene efecto propio medible en NINGUNO de
# los 7 vigentes (0 de 7; máximo t=+1.51 en CREDITC1, multifactor Newey-West).
# CONTROL DE QUE EL MÉTODO FUNCIONA: sobre BUENAVC1 el oro sale con t=+5.57 y
# beta=+1.20. Si alguna vez vuelve una minera de oro al universo, se reincorpora
# descomentando la línea.
# OJO — ESTA ES LA FUENTE DE VERDAD, no config.yaml. El listado de series de
# config.yaml es informativo y NO se lee desde acá; divergieron durante un mes
# sin que nada avisara. Al tocar una hay que tocar la otra.
_SERIES: dict[str, tuple[str, str]] = {
    "macro_cobre":     ("PD04701XD", "D"),
    # "macro_oro":     ("PD04704XD", "D"),   # eliminado 2026-09-01, ver arriba
    "macro_embi":      ("PD04709XD", "D"),
    "macro_tasa_ref":  ("PD04722MM", "M"),
    "macro_inflacion": ("PN01271PM", "M"),
}

# ── Índices externos (acta 2026-09-02 §B2) ───────────────────────────────────
# NO REQUIEREN BLOOMBERG: son gratis y el proyecto ya usa yfinance. El acta lo
# dice explícitamente ("LOS ÍNDICES EXTERNOS NO REQUIEREN BLOOMBERG").
#
# POR QUÉ ENTRAN. El factor común medido del universo es ~30% diario y ~45%
# mensual (PCA, scripts/mide_comovimiento_oe1.py), y las cinco series BCRP
# explican como mucho ~12%. Ese hueco es donde vivirían estos índices — o es
# flujo local que ninguna fuente pública muestra. Las dos respuestas son
# publicables, y por eso se MIDEN en vez de suponerse: pasan por el mismo tamiz
# que descartó al oro y al estaño (Newey-West, aporte incremental).
#
# LA CAUSALIDAD, Y ES EL PUNTO DELICADO. El NYSE cierra DESPUÉS que la BVL
# (BVL ~15:00 Lima; NYSE 16:00 ET). Entonces el cierre del S&P del día d NO está
# disponible cuando cierra la BVL el día d.
#   * Usar SPX(d) para explicar el retorno de la BVL en d sería FUGA.
#   * Pero por D13 la observación de d se EJECUTA al cierre de d+1, y para
#     entonces SPX(d) lleva ~18 horas siendo público. Por eso la columna entra
#     SIN rezago adicional y sigue siendo causal: el rezago ya está en el reloj
#     del entorno, no hace falta duplicarlo.
# Este argumento NO depende del hallazgo "la BVL reacciona con un día de rezago",
# que quedó en revisión por el desfase de fechas (ver
# docs/hallazgos_desfase_fecha_bvl.txt §2.c). Depende solo del horario de cierre.
#
# DXY NO SE INCLUYE: es casi colineal con macro_tc_usdpen, que ya está. Si algún
# día entra, se mide el aporte INCREMENTAL, no se agrega a ciegas.
_INDICES: dict[str, str] = {
    "macro_spx":     "^GSPC",   # S&P 500
    "macro_msci_em": "EEM",     # iShares MSCI Emerging Markets (proxy líquido)
}

_CACHE_IDX = Path("data/interim/macro_indices.parquet")

_cache_df: pd.DataFrame | None = None
_cache_idx: pd.DataFrame | None = None


def load_indices(start: str = "2011-01-01", end: str = "2025-12-31",
                 cache: Path = _CACHE_IDX, refresh: bool = False) -> pd.DataFrame:
    """Descarga (o lee de caché) los índices externos. NIVELES CRUDOS.

    Mismo contrato que `load_macro`: niveles, tz-naive, indexado por fecha. La
    transformación (retorno log, razón contra media móvil) va en OE1, igual que
    con el resto del canal — R6 entrega crudo.
    """
    global _cache_idx
    if _cache_idx is not None and not refresh:
        return _cache_idx
    if cache.exists() and not refresh:
        _cache_idx = pd.read_parquet(cache)
        return _cache_idx

    import yfinance as yf

    cols = {}
    for feat, ticker in _INDICES.items():
        h = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
        if h.empty:
            print(f"[macro] {feat} ({ticker}): sin datos; se omite la columna.")
            continue
        s = h["Close"].copy()
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        cols[feat] = s[~s.index.duplicated(keep="last")]

    if not cols:
        raise RuntimeError("no se pudo descargar ningún índice externo")

    df = pd.DataFrame(cols).sort_index()
    df.index.name = "date"
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache)
    _cache_idx = df
    return df


def _parse_daily(name: str) -> pd.Timestamp:
    """'02.Ene.20' -> Timestamp('2020-01-02')."""
    day, mon, yy = name.split(".")
    return pd.Timestamp(year=2000 + int(yy), month=_MONTHS[mon], day=int(day))


def _parse_monthly(name: str) -> pd.Period:
    """'Ene.2020' -> Period('2020-01', 'M')."""
    mon, yyyy = name.split(".")
    return pd.Period(year=int(yyyy), month=_MONTHS[mon], freq="M")


def _download_series(code: str, freq: str, start: str, end: str) -> pd.Series:
    import requests

    url = _BCRP_URL.format(code=code, start=start, end=end)
    resp = requests.get(url, headers=_HEADERS, timeout=90)
    resp.raise_for_status()
    periods = resp.json()["periods"]
    idx, vals = [], []
    for it in periods:
        v = it["values"][0]
        if v in ("n.d.", "", None):
            continue
        if freq == "D":
            idx.append(_parse_daily(it["name"]))
        else:  # mensual -> known_date de publicación (point-in-time)
            per = _parse_monthly(it["name"])
            if code == "PN01271PM":       # IPC: publicado ~1 del mes siguiente
                idx.append((per + 1).to_timestamp(how="start"))
            else:                          # tasa: conocida a fin de su propio mes
                idx.append(per.to_timestamp(how="end").normalize())
        vals.append(float(v))
    return pd.Series(vals, index=pd.DatetimeIndex(idx)).sort_index()


def load_macro(start: str = "2011-01-01", end: str = "2025-12-31",
               cache: Path = _CACHE, refresh: bool = False) -> pd.DataFrame:
    """Descarga (o lee de caché) las 5 series BCRP + el TC (de src.market.fx),
    cada una en su índice de fechas efectivas (known_date). tz-naive.

    Devuelve un DataFrame con columnas _SERIES + 'macro_tc_usdpen', indexado por
    la unión de fechas (con NaN donde una serie no observa). Se cachea en parquet.

    `start` = 2011 (y NO 2012, inicio del panel) a propósito: las series MENSUALES
    se fechan en su publicación (tasa a fin de su mes, IPC el 1 del mes siguiente),
    así que sin un año de colchón el `asof` de macro_features deja sin valor todo
    enero-2012 (medido: 21 días hábiles de macro_tasa_ref y 22 de macro_inflacion).
    El colchón NO introduce look-ahead: solo aporta observaciones ANTERIORES al
    horizonte. Si se cambia este default hay que regenerar el caché (refresh=True).
    """
    global _cache_df
    if _cache_df is not None and not refresh:
        return _cache_df
    if cache.exists() and not refresh:
        _cache_df = pd.read_parquet(cache)
        return _cache_df

    cols = {}
    for feat, (code, freq) in _SERIES.items():
        cols[feat] = _download_series(code, freq, start, end)

    # TC desde el módulo ya existente (misma fuente BCRP, serie PD04640PD)
    from src.market import fx
    cols["macro_tc_usdpen"] = fx.load_usdpen(start, end)

    df = pd.DataFrame(cols).sort_index()
    df.index.name = "date"
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache)
    _cache_df = df
    return df


def macro_features(dates) -> pd.DataFrame:
    """Alinea las series macro a un índice de fechas bursátiles (el calendario de
    R6), con convención `asof` (último valor conocido <= fecha) por serie —
    resuelve fines de semana/feriados y el rezago de publicación de las mensuales.

    Devuelve un DataFrame indexado por `dates` con una columna por feature macro
    (NIVELES CRUDOS; la transformación va en OE1).
    """
    macro = load_macro()
    # Los índices externos se concatenan y se alinean con el MISMO `asof`: un
    # feriado de la BVL que no lo es en Nueva York deja el dato disponible, y un
    # feriado de Nueva York arrastra el último cierre conocido. Es el
    # comportamiento correcto en los dos sentidos.
    try:
        macro = pd.concat([macro, load_indices()], axis=1).sort_index()
    except Exception as exc:  # noqa: BLE001 - el canal externo es opcional
        print(f"[macro] índices externos no disponibles ({exc}); se sigue sin ellos.")

    idx = pd.DatetimeIndex(dates)
    out = {}
    for col in macro.columns:
        s = macro[col].dropna()
        out[col] = [s.asof(d) for d in idx]
    return pd.DataFrame(out, index=idx)
