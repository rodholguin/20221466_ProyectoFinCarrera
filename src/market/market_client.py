"""R3 — Pipeline de datos de mercado (OHLCV).

Estrategia: BVL como fuente PRIMARIA (oficial), Yahoo como FALLBACK, y
reconciliación de cierres entre ambas para auditar calidad. Cada fila lleva
una columna `source` para saber de dónde salió.

Limitaciones honestas:
  * La BVL no expone un REST público y documentado de OHLCV histórico. Hay
    que (a) probar la familia dataondemand v1, o (b) capturar el endpoint XHR
    del sitio con las DevTools del navegador (pestaña Network/Fetch) y pegarlo
    en `_BVL_QUOTES_ENDPOINT`. Por eso esto queda como TODO con la estructura
    lista.
  * Yahoo cubre bien BAP y BVN (NYSE) pero de forma irregular las acciones
    solo-BVL (sufijo ".LM"). De ahí que sea el respaldo, no la primaria.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.universe import MARKET_SCHEMA, Asset

# --------------------------------------------------------------------------
# Yahoo (fallback)
# --------------------------------------------------------------------------
def fetch_yahoo(asset: Asset, start: str, end: str) -> pd.DataFrame:
    """Descarga OHLCV diario desde Yahoo y lo normaliza al esquema canónico."""
    import yfinance as yf  # import local: dependencia opcional

    if not asset.yahoo:
        return pd.DataFrame(columns=MARKET_SCHEMA)

    df = yf.download(asset.yahoo, start=start, end=end, auto_adjust=False,
                     progress=False)
    if df.empty:
        return pd.DataFrame(columns=MARKET_SCHEMA)

    df = df.reset_index().rename(columns={
        "Date": "date", "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    df["ticker"] = asset.bvl
    df["source"] = "yahoo"
    return df[MARKET_SCHEMA]


# --------------------------------------------------------------------------
# BVL (primaria)
# --------------------------------------------------------------------------
# TODO: reemplazar por el endpoint real. Capturarlo así:
#   1. Abrir https://www.bvl.com.pe -> ficha del valor (p.ej. ALICORC1)
#   2. DevTools > Network > filtro Fetch/XHR
#   3. Ver la llamada JSON del histórico de cotizaciones; copiar URL + payload
# La maestría usó POST contra dataondemand.bvl.com.pe/v1/financialstatements/
# para EEFF, así que probar primero la misma familia /v1 para precios.
_BVL_QUOTES_ENDPOINT = "https://dataondemand.bvl.com.pe/v1/quotes/"  # TODO verificar


def fetch_bvl(asset: Asset, start: str, end: str) -> pd.DataFrame:
    """Descarga OHLCV diario desde la BVL. Esqueleto: completar el contrato."""
    import requests

    payload = {                       # TODO: ajustar al contrato real del endpoint
        "symbol": asset.bvl,
        "from": start,
        "to": end,
    }
    try:
        resp = requests.post(_BVL_QUOTES_ENDPOINT, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # red no disponible en sandbox; manejar en local
        print(f"[BVL] {asset.bvl}: fallo ({exc}). Usar fallback Yahoo.")
        return pd.DataFrame(columns=MARKET_SCHEMA)

    # TODO: mapear la estructura JSON real a estas columnas.
    df = pd.DataFrame(data)  # placeholder
    if df.empty:
        return df.reindex(columns=MARKET_SCHEMA)
    df["ticker"] = asset.bvl
    df["source"] = "bvl"
    return df.reindex(columns=MARKET_SCHEMA)


# --------------------------------------------------------------------------
# Orquestación + reconciliación
# --------------------------------------------------------------------------
def fetch_market(asset: Asset, start: str, end: str, raw_dir: Path) -> pd.DataFrame:
    """Primaria BVL; si viene vacía o incompleta, completa con Yahoo.

    Guarda ambos crudos en disco (cache) y reporta discrepancias de cierre.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    bvl = fetch_bvl(asset, start, end)
    yah = fetch_yahoo(asset, start, end)

    for name, df in (("bvl", bvl), ("yahoo", yah)):
        if not df.empty:
            df.to_parquet(raw_dir / f"market_{asset.bvl}_{name}.parquet")

    if not bvl.empty and not yah.empty:
        _report_discrepancies(asset, bvl, yah)

    primary = bvl if not bvl.empty else yah
    if primary.empty:
        print(f"[market] {asset.bvl}: SIN DATOS en ninguna fuente.")
    return primary


def _report_discrepancies(asset: Asset, bvl: pd.DataFrame, yah: pd.DataFrame,
                          tol: float = 0.01) -> None:
    """Compara cierres BVL vs Yahoo y reporta diferencias > tolerancia."""
    m = bvl.merge(yah, on="date", suffixes=("_bvl", "_yahoo"))
    if m.empty:
        return
    rel = (m["close_bvl"] - m["close_yahoo"]).abs() / m["close_yahoo"].replace(0, pd.NA)
    bad = m[rel > tol]
    if len(bad):
        print(f"[reconcile] {asset.bvl}: {len(bad)} días con diff de cierre > {tol:.0%}")


if __name__ == "__main__":
    from src.universe import Config

    cfg = Config.load()
    for a in cfg.assets:
        df = fetch_market(a, cfg.start, cfg.end, Path(cfg.paths["raw"]))
        print(f"{a.bvl}: {len(df)} filas")
