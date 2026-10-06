"""Verifica la MONEDA de los tickers Yahoo .LM contra el close CRUDO de la BVL.

Critico para INRETC1: cotiza en US$ en la BVL y el pipeline lo convierte a PEN
(market_client._to_pen). Si Yahoo lo entregara en una moneda distinta a la capa
cruda, fusionar su OHLC/volumen introduciria un salto de escala.

Metodo: no confiar en fast_info (devolvio '?'); comparar el nivel del close de
Yahoo con el close crudo de la BVL en fechas comunes. Razon ~1.0 => misma moneda.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf

from src.universe import Config

TICKERS = {
    "MINSURI1": "MINSURI1.LM",
    "INRETC1":  "INRETC1.LM",
    "CPACASC1": "CPACASC1.LM",
    "FERREYC1": "FERREYC1.LM",
    "LUSURC1":  "LUSURC1.LM",
    "ALICORC1": "ALICORC1.LM",   # control: ya en uso, PEN
    "CREDITC1": "CREDITC1.LM",   # control: ya en uso, PEN
}

START, END = "2024-01-01", "2025-12-31"


def bvl_close(cfg, asset) -> pd.DataFrame:
    """Lee la capa CRUDA de la BVL si existe en disco; si no, la descarga."""
    from src.market.market_client import fetch_bvl

    raw = Path(cfg.paths["raw"]) / f"market_{asset.bvl}_bvl.parquet"
    if raw.exists():
        df = pd.read_parquet(raw)
        print(f"    (capa cruda en disco: {raw.name})")
    else:
        df = fetch_bvl(asset, START, END)
    if df.empty:
        return df
    df = df[["date", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df


def main() -> None:
    cfg = Config.load("config.yaml")
    by_bvl = {a.bvl: a for a in cfg.assets}

    print(f"Comparacion nivel Yahoo vs close CRUDO BVL, {START}..{END}\n")
    print(f"  {'activo':10s} {'ticker':14s} {'moneda_info':12s} {'n_comun':>7s} "
          f"{'ratio_med':>9s}  veredicto")

    for bvl, tk in TICKERS.items():
        asset = by_bvl.get(bvl)
        if asset is None:
            print(f"  {bvl:10s} NO esta en config.yaml")
            continue

        t = yf.Ticker(tk)
        moneda = "?"
        try:
            moneda = (t.info or {}).get("currency") or "?"
        except Exception:
            pass

        try:
            yah = t.history(start=START, end=END, auto_adjust=False)
        except Exception as exc:
            print(f"  {bvl:10s} {tk:14s} ERROR yahoo: {exc}")
            continue
        if yah is None or yah.empty:
            print(f"  {bvl:10s} {tk:14s} sin datos yahoo")
            continue

        y = yah.reset_index()[["Date", "Close"]].rename(
            columns={"Date": "date", "Close": "y_close"})
        s = pd.to_datetime(y["date"])
        if s.dt.tz is not None:
            s = s.dt.tz_convert(None)
        y["date"] = s.dt.normalize()

        b = bvl_close(cfg, asset)
        if b.empty:
            print(f"  {bvl:10s} {tk:14s} sin close BVL")
            continue
        b = b[(b["date"] >= START) & (b["date"] <= END)]

        m = y.merge(b, on="date", how="inner")
        m = m[(m["close"] > 0) & (m["y_close"] > 0)]
        if m.empty:
            print(f"  {bvl:10s} {tk:14s} sin fechas comunes")
            continue

        ratio = float((m["y_close"] / m["close"]).median())
        if 0.97 <= ratio <= 1.03:
            veredicto = "MISMA moneda que la capa cruda BVL"
        elif 3.0 <= ratio <= 4.2:
            veredicto = "Yahoo en PEN, BVL cruda en USD (ratio ~ TC)"
        elif 0.24 <= ratio <= 0.34:
            veredicto = "Yahoo en USD, BVL cruda en PEN (ratio ~ 1/TC)"
        else:
            veredicto = "DISTINTO (revisar: splits/base de acciones?)"

        print(f"  {bvl:10s} {tk:14s} {moneda:12s} {len(m):7d} {ratio:9.4f}  {veredicto}")
        print(f"      nivel mediano  yahoo={m['y_close'].median():10.2f}   "
              f"bvl_crudo={m['close'].median():10.2f}")


if __name__ == "__main__":
    main()
