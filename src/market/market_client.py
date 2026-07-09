"""R3 — Pipeline de datos de mercado (OHLCV) + capa de acciones corporativas.

Fuentes:
  - BVL primaria : GET dataondemand.bvl.com.pe/v1/stock-quote/share-values/{nemonico}
                   Endpoint descubierto en el bundle Angular del sitio (main.js).
                   Devuelve precio de cierre diario (referencial oficial) desde 2012-01-02.
                   Limitacion: solo close; open=high=low=close, volume=NaN.
                   BVL determina el horizonte EFECTIVO del dataset de mercado
                   (2012-2025): es la fuente "sana y original" (BVL/SMV) que
                   manda sobre Yahoo. No se usan datos de mercado anteriores a
                   2012 (solo Yahoo) en el dataset final.
  - Yahoo (enriquecimiento puntual): SOLO completa open/high/low/volumen en
                   fechas donde BVL YA tiene un registro (mismo instrumento;
                   no aplica a BUENAVC1/BVN, que es un ADR USD). NO se usa para
                   extender la cobertura hacia atrás del inicio de BVL: para
                   tickers de baja liquidez (CREDITC1) se confirmó que el close
                   de Yahoo en el período pre-BVL viene en una base de acciones
                   distinta (ajustada a la fecha de descarga, no a la fecha
                   cotizada -- ver corporate_actions.py), y mezclarlo generaba
                   saltos artificiales >100%. Por eso el open/high/low de Yahoo
                   se reescala por el factor acumulado de splits antes de
                   fusionarlo con el close (siempre autoritativo) de la BVL.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.market.corporate_actions import (
    build_adjusted_prices, fetch_actions, filter_actions_by_cutoff, split_factor,
)
from src.universe import MARKET_SCHEMA, Asset

# ── BVL (primaria) ────────────────────────────────────────────────────────────
_BVL_SHAREVALUES_URL = "https://dataondemand.bvl.com.pe/v1/stock-quote/share-values"
_BVL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": "https://www.bvl.com.pe",
    "Referer": "https://www.bvl.com.pe/",
    "Accept": "application/json, text/plain, */*",
}


def fetch_bvl(asset: Asset, start: str, end: str) -> pd.DataFrame:
    """Descarga precios de cierre diarios desde la BVL (share-values).

    Endpoint: GET /v1/stock-quote/share-values/{nemonico}?startDate=...&endDate=...
    Cobertura: 2012-01-02 en adelante para todos los activos del universo.
    Limitacion: solo precio de cierre (referencial oficial);
                open=high=low=close, volume=NaN.
    """
    import requests

    try:
        resp = requests.get(
            f"{_BVL_SHAREVALUES_URL}/{asset.bvl}",
            params={"startDate": start, "endDate": end},
            headers=_BVL_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[BVL] {asset.bvl}: fallo ({exc}). Usar fallback Yahoo.")
        return pd.DataFrame(columns=MARKET_SCHEMA)

    values = data.get("values", [])
    if not values:
        print(f"[BVL] {asset.bvl}: sin datos en {start}-{end}.")
        return pd.DataFrame(columns=MARKET_SCHEMA)

    df = pd.DataFrame(values, columns=["date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df[df["close"] > 0].copy()   # filtrar cierres 0 (días sin referencia)
    df["open"] = df["close"]
    df["high"] = df["close"]
    df["low"] = df["close"]
    df["volume"] = float("nan")
    df["ticker"] = asset.bvl
    df["source"] = "bvl"
    return df[MARKET_SCHEMA]


# ── Yahoo (fallback / enriquecimiento OHLCV) ─────────────────────────────────
def fetch_yahoo(asset: Asset, start: str, end: str) -> pd.DataFrame:
    """Descarga OHLCV diario desde Yahoo y lo normaliza al esquema canonico.

    Usa Ticker.history() para evitar el MultiIndex de yfinance >= 0.2.38.
    """
    import yfinance as yf

    if not asset.yahoo:
        return pd.DataFrame(columns=MARKET_SCHEMA)

    try:
        raw = yf.Ticker(asset.yahoo).history(start=start, end=end, auto_adjust=False)
    except Exception as exc:
        print(f"[Yahoo] {asset.yahoo}: fallo ({exc}).")
        return pd.DataFrame(columns=MARKET_SCHEMA)

    if raw.empty:
        return pd.DataFrame(columns=MARKET_SCHEMA)

    df = raw.reset_index().rename(columns={
        "Date": "date", "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    # history() devuelve Date tz-aware; normalizar a datetime tz-naive por dia.
    s = pd.to_datetime(df["date"])
    if s.dt.tz is not None:
        s = s.dt.tz_convert(None)
    df["date"] = s.dt.normalize()
    df["ticker"] = asset.bvl
    df["source"] = "yahoo"
    return df[MARKET_SCHEMA]


# ── Orquestacion y merge ──────────────────────────────────────────────────────
def fetch_market(asset: Asset, start: str, end: str, raw_dir: Path) -> pd.DataFrame:
    """Obtiene datos de mercado: BVL primaria (determina el horizonte) +
    Yahoo como enriquecimiento puntual de OHLCV + capa de acciones corporativas.

    Estrategia:
      - Sin datos BVL -> sin datos de mercado (Yahoo no es un fallback de
        cobertura; ver docstring del módulo).
      - Con BVL: close oficial de la BVL; OHLCV enriquecido con Yahoo en las
        fechas donde coinciden, si es el mismo instrumento en PEN (no aplica
        para BUENAVC1/BVN USD).
      - Tras consolidar close_raw, se agregan close_split_adj y
        close_total_return (ver corporate_actions.py).
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    bvl = fetch_bvl(asset, start, end)
    yah = fetch_yahoo(asset, start, end)

    for name, df in (("bvl", bvl), ("yahoo", yah)):
        if not df.empty:
            df.to_parquet(raw_dir / f"market_{asset.bvl}_{name}.parquet")

    if bvl.empty:
        print(f"[market] {asset.bvl}: SIN DATOS en la BVL (fuente primaria) -> "
              f"sin datos de mercado (Yahoo no reemplaza a la BVL como fuente).")
        return pd.DataFrame(columns=MARKET_SCHEMA)

    # BVN (BUENAVC1 Yahoo) es ADR NYSE en USD != BUENAVC1 BVL en PEN.
    same_instrument = (asset.bvl != "BUENAVC1")
    actions = fetch_actions(asset)
    actions = filter_actions_by_cutoff(actions, end, bvl["date"])

    if not yah.empty and same_instrument:
        merged = _merge_bvl_yahoo(bvl, yah, splits=actions["splits"])
    else:
        merged = bvl.copy()

    result = _add_corporate_actions(asset, merged, end, actions=actions)

    if not yah.empty and same_instrument:
        _report_discrepancies(asset, result, yah)

    return result


def _merge_bvl_yahoo(bvl: pd.DataFrame, yah: pd.DataFrame,
                     splits: pd.Series | None = None) -> pd.DataFrame:
    """Enriquece BVL (close SIEMPRE autoritativo) con open/high/low/volumen de
    Yahoo en las fechas donde ambas fuentes coinciden.

    Si `splits` no es None/vacío, el open/high/low de Yahoo se reescala por el
    factor acumulado de splits antes de fusionar: para tickers de baja
    liquidez (CREDITC1), ese open/high/low viene en la base de acciones
    "actual" (a la fecha de descarga), no en la vigente el día cotizado, y
    mezclarlo sin reescalar generaría un OHLC inconsistente con el close de
    BVL en la misma fila (ver corporate_actions.py).
    """
    yah_ohlc = yah[["date", "open", "high", "low", "volume"]].copy()

    if splits is not None and not splits.empty:
        factor = split_factor(yah_ohlc["date"], splits).to_numpy()
        for col in ("open", "high", "low"):
            yah_ohlc[col] = yah_ohlc[col].to_numpy() * factor

    merged = bvl.merge(yah_ohlc, on="date", how="left", suffixes=("", "_yah"))
    for col in ("open", "high", "low", "volume"):
        yah_col = f"{col}_yah"
        if yah_col in merged.columns:
            merged[col] = merged[yah_col].combine_first(merged[col])
            merged.drop(columns=[yah_col], inplace=True)
    return merged


def _add_corporate_actions(asset: Asset, df: pd.DataFrame, end: str | None,
                           actions: dict[str, pd.Series]) -> pd.DataFrame:
    """Agrega close_raw, close_split_adj, close_total_return y los flags
    is_split_adjusted/is_div_adjusted (ver corporate_actions.build_adjusted_prices)."""
    df = df.sort_values("date").reset_index(drop=True)
    df["close_raw"] = df["close"]

    close_indexed = pd.Series(df["close_raw"].to_numpy(), index=pd.DatetimeIndex(df["date"]))
    close_split_adj, close_total_return, flags = build_adjusted_prices(
        asset, close_indexed, end=end, actions=actions)

    df["close_split_adj"] = close_split_adj.to_numpy()
    df["close_total_return"] = close_total_return.to_numpy()
    df["is_split_adjusted"] = flags["is_split_adjusted"]
    df["is_div_adjusted"] = flags["is_div_adjusted"]
    return df


def _report_discrepancies(asset: Asset, merged: pd.DataFrame, yah: pd.DataFrame,
                          tol: float = 0.02) -> None:
    """Compara close_split_adj (BVL ajustado por splits) vs. close de Yahoo en
    fechas solapadas. close_split_adj es comparable con el close de Yahoo con
    auto_adjust=False: ambos quedan ajustados por splits a la fecha de
    descarga pero NO por dividendos -- el close crudo de BVL, en cambio,
    difiere de Yahoo por los splits acumulados desde cada fecha."""
    m = merged[["date", "close_split_adj"]].merge(
        yah[["date", "close"]], on="date")
    if m.empty:
        return
    rel = (m["close_split_adj"] - m["close"]).abs() / m["close"].replace(0, pd.NA)
    bad = m[rel > tol]
    if len(bad):
        print(f"[reconcile] {asset.bvl}: {len(bad)} dias con diff "
              f"(close_split_adj vs Yahoo) > {tol:.0%} (de {len(m)} solapados)")


# Ejecutar el pipeline completo con: python -m src.market
