"""R3 — Pipeline de datos de mercado (OHLCV).

Fuentes:
  - BVL primaria : GET dataondemand.bvl.com.pe/v1/stock-quote/share-values/{nemonico}
                   Endpoint descubierto en el bundle Angular del sitio (main.js).
                   Devuelve precio de cierre diario (referencial oficial) desde 2012-01-02.
                   Limitacion: solo close; open=high=low=close, volume=NaN.
  - Yahoo fallback: cubre el periodo pre-2012 para tickers con sufijo .LM,
                   y da OHLCV completo para enriquecer los registros BVL.
                   Nota: BVN (BUENAVC1) es un ADR NYSE en USD -> instrumento
                   diferente; se guarda como raw para referencia pero NO se mezcla
                   con los precios BVL en PEN.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

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
    """Obtiene datos de mercado fusionando BVL (primaria) con Yahoo (complemento).

    Estrategia de merge:
      - Fechas BVL (2012+): close oficial de la BVL; OHLCV enriquecido con Yahoo
        si es el mismo instrumento en PEN (no aplica para BUENAVC1/BVN USD).
      - Fechas solo Yahoo (pre-2012): OHLCV completo de Yahoo.
      - Si solo BVL: close-only.
      - Si solo Yahoo: OHLCV completo.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    bvl = fetch_bvl(asset, start, end)
    yah = fetch_yahoo(asset, start, end)

    for name, df in (("bvl", bvl), ("yahoo", yah)):
        if not df.empty:
            df.to_parquet(raw_dir / f"market_{asset.bvl}_{name}.parquet")

    if bvl.empty and yah.empty:
        print(f"[market] {asset.bvl}: SIN DATOS en ninguna fuente.")
        return pd.DataFrame(columns=MARKET_SCHEMA)

    if bvl.empty:
        return yah

    if yah.empty:
        return bvl

    # BVN (BUENAVC1 Yahoo) es ADR NYSE en USD != BUENAVC1 BVL en PEN.
    # No mezclar precios de distintos instrumentos; Yahoo solo aporta el periodo pre-BVL.
    same_instrument = (asset.bvl != "BUENAVC1")

    merged = _merge_bvl_yahoo(bvl, yah, enrich_ohlcv=same_instrument)

    if same_instrument:
        _report_discrepancies(asset, bvl, yah)

    return merged


def _merge_bvl_yahoo(bvl: pd.DataFrame, yah: pd.DataFrame,
                     enrich_ohlcv: bool = True) -> pd.DataFrame:
    """Combina BVL close (primario) con Yahoo OHLCV (complemento).

    - Fechas solo en Yahoo (pre-2012): fila Yahoo completa.
    - Fechas en BVL: close de BVL; si enrich_ohlcv, open/high/low/volume de Yahoo.
    """
    bvl_dates = set(bvl["date"])

    pre_bvl = yah[~yah["date"].isin(bvl_dates)].copy()

    if enrich_ohlcv:
        overlap = bvl.merge(
            yah[["date", "open", "high", "low", "volume"]],
            on="date", how="left", suffixes=("", "_yah"),
        )
        for col in ["open", "high", "low", "volume"]:
            yah_col = col + "_yah"
            if yah_col in overlap.columns:
                overlap[col] = overlap[yah_col].combine_first(overlap[col])
                overlap.drop(columns=[yah_col], inplace=True)
        bvl_part = overlap
    else:
        bvl_part = bvl

    combined = pd.concat([pre_bvl, bvl_part], ignore_index=True)
    return combined.sort_values("date").reset_index(drop=True)


def _report_discrepancies(asset: Asset, bvl: pd.DataFrame, yah: pd.DataFrame,
                          tol: float = 0.02) -> None:
    """Compara cierres BVL vs Yahoo en el periodo solapado y reporta diffs > tol."""
    m = bvl.merge(yah, on="date", suffixes=("_bvl", "_yahoo"))
    if m.empty:
        return
    rel = (m["close_bvl"] - m["close_yahoo"]).abs() / m["close_yahoo"].replace(0, pd.NA)
    bad = m[rel > tol]
    if len(bad):
        print(f"[reconcile] {asset.bvl}: {len(bad)} dias con diff de cierre > {tol:.0%}"
              f" (de {len(m)} solapados)")


# Ejecutar el pipeline completo con: python -m src.market
