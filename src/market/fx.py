"""Tipo de cambio USD/PEN del BCRP para convertir a PEN los dividendos que la
BVL declara en US$ (BUENAVC1 completo; CORAREC1 parcial) al construir
close_total_return.

Fuente oficial: Banco Central de Reserva del Perú (BCRP), serie diaria
PD04640PD = "Tipo de cambio - venta - bancario" (Nuevos Soles por US$). Se
eligió esta serie por su cobertura larga (2010+) y por ser la fuente estatal
peruana, coherente con el principio del proyecto ("BVL/SMV/BCRP mandan sobre
fuentes externas"). El close de mercado de la BVL para estos activos está en
PEN (verificado por magnitud: BUENAVC1 med ~S/41), por lo que el dividendo en
US$ debe llevarse a PEN al tipo de cambio de su fecha de corte para que el
factor de reinversión (1 + div/precio) sea homogéneo en soles.

El API del BCRP devuelve los periodos diarios con nombre "DD.Mmm.YY" en español
(meses abreviados, con "Set" para setiembre) y "n.d." en feriados; se cachea la
serie ya parseada en data/interim/fx_usdpen_bcrp.parquet para reproducibilidad
y para no depender de la red en cada corrida.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

_BCRP_SERIES = "PD04640PD"  # Tipo de cambio - venta - bancario (S/ por US$), diario
_BCRP_URL = ("https://estadisticas.bcrp.gob.pe/estadisticas/series/api/"
             "{series}/json/{start}/{end}")
_CACHE = Path("data/interim/fx_usdpen_bcrp.parquet")
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}

# Abreviaturas de mes del BCRP (español). OJO: setiembre = "Set" (no "Sep").
_MONTHS = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
           "Jul": 7, "Ago": 8, "Set": 9, "Oct": 10, "Nov": 11, "Dic": 12}

_PEN_COINS = {"S/.", "S/", "PEN", "SOLES"}
_USD_COINS = {"US$", "USD", "$", "DOLARES", "DÓLARES"}

_series_cache: pd.Series | None = None


def _parse_period(name: str) -> pd.Timestamp:
    """'02.Ene.20' -> Timestamp('2020-01-02'). El BCRP usa año de 2 dígitos."""
    day, mon, yy = name.split(".")
    return pd.Timestamp(year=2000 + int(yy), month=_MONTHS[mon], day=int(day))


def _download(start: str, end: str) -> pd.Series:
    import requests

    url = _BCRP_URL.format(series=_BCRP_SERIES, start=start, end=end)
    resp = requests.get(url, headers=_HEADERS, timeout=90)
    resp.raise_for_status()
    periods = resp.json()["periods"]
    dates, rates = [], []
    for it in periods:
        val = it["values"][0]
        if val == "n.d.":  # feriado: sin cotización ese día
            continue
        dates.append(_parse_period(it["name"]))
        rates.append(float(val))
    s = pd.Series(rates, index=pd.DatetimeIndex(dates), name="usdpen").sort_index()
    return s


def load_usdpen(start: str = "2010-01-01", end: str = "2026-12-31",
                cache: Path = _CACHE, refresh: bool = False) -> pd.Series:
    """Serie diaria S/ por US$ (venta bancario, BCRP), tz-naive, ordenada.

    Se cachea en `cache` (parquet). Con `refresh=True` fuerza la descarga y
    regraba el cache. Días sin cotización (feriados) NO están en el índice; usar
    `rate_asof` para obtener el último tipo de cambio vigente en o antes de una
    fecha dada.
    """
    global _series_cache
    if _series_cache is not None and not refresh:
        return _series_cache

    if cache.exists() and not refresh:
        _series_cache = pd.read_parquet(cache)["usdpen"]
        return _series_cache

    s = _download(start, end)
    cache.parent.mkdir(parents=True, exist_ok=True)
    s.to_frame().to_parquet(cache)
    _series_cache = s
    return s


def rate_asof(dates: pd.DatetimeIndex) -> pd.Series:
    """Tipo de cambio vigente en o antes de cada fecha (convención `Series.asof`:
    último dato disponible <= fecha). Resuelve feriados/fines de semana usando la
    cotización hábil previa."""
    fx = load_usdpen()
    idx = pd.DatetimeIndex(dates)
    return pd.Series([fx.asof(d) for d in idx], index=idx, name="usdpen")


def is_pen(coin: str | None) -> bool:
    return (coin or "").strip().upper() in {c.upper() for c in _PEN_COINS}


def is_usd(coin: str | None) -> bool:
    return (coin or "").strip().upper() in {c.upper() for c in _USD_COINS}
