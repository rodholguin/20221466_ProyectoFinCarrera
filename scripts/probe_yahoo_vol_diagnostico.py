"""Diagnostico final del volumen Yahoo: en que se puede confiar y en que no.

De las pruebas previas quedaron 3 cosas por cuantificar:

  A. FILAS FANTASMA: Yahoo emite filas en dias en que la BVL NO cotizo (se vio
     28 y 29 de julio, feriados de Fiestas Patrias, con close arrastrado y
     volumen 0). Cuantas son y cuantas traen volumen > 0?
  B. CEROS vs AÑO: los dias con volumen=0 y precio BVL que SI cambio, se
     concentran en los primeros años (calidad que degrada hacia atras) o estan
     repartidos? Determina si el dato reciente es utilizable aunque el viejo no.
  C. MAGNITUD: en esos dias contradictorios, cuanto se movio el precio? Si son
     movimientos minusculos, es ruido de redondeo del cierre referencial; si son
     grandes, Yahoo se esta perdiendo operaciones reales.
  D. TEST 6 CORREGIDO: los cuartiles de |retorno| colapsaban porque hay miles de
     retornos exactamente 0 (precio stale). Se recalcula excluyendolos.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from src.universe import Config

TICKERS = {
    "MINSURI1": "MINSURI1.LM",
    "INRETC1":  "INRETC1.LM",
    "CPACASC1": "CPACASC1.LM",
    "FERREYC1": "FERREYC1.LM",
    "LUSURC1":  "LUSURC1.LM",
    "ALICORC1": "ALICORC1.LM",
    "CREDITC1": "CREDITC1.LM",
}
START, END = "2012-01-01", "2025-12-31"


def yahoo_hist(tk: str) -> pd.DataFrame:
    raw = yf.Ticker(tk).history(start=START, end=END, auto_adjust=False)
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.reset_index()[["Date", "Close", "Volume"]].rename(
        columns={"Date": "date", "Close": "y_close", "Volume": "y_vol"})
    s = pd.to_datetime(df["date"])
    if s.dt.tz is not None:
        s = s.dt.tz_convert(None)
    df["date"] = s.dt.normalize()
    return df


def bvl_hist(cfg, asset) -> pd.DataFrame:
    from src.market.market_client import fetch_bvl

    p = Path(cfg.paths["raw"]) / f"market_{asset.bvl}_bvl.parquet"
    df = pd.read_parquet(p) if p.exists() else fetch_bvl(asset, START, END)
    if df.empty:
        return df
    df = df[["date", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df.sort_values("date")


def main() -> None:
    cfg = Config.load("config.yaml")
    by_bvl = {a.bvl: a for a in cfg.assets}
    datos: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    for nem, tk in TICKERS.items():
        a = by_bvl.get(nem)
        if a is None:
            continue
        y, b = yahoo_hist(tk), bvl_hist(cfg, a)
        if not y.empty and not b.empty:
            datos[nem] = (y, b[(b["date"] >= START) & (b["date"] <= END)])

    # ── A. filas fantasma ────────────────────────────────────────────────────
    print("=" * 78)
    print("A. FILAS FANTASMA: Yahoo en fechas donde la BVL no cotizo")
    print("=" * 78)
    print(f"  {'activo':10s} {'filas Yahoo':>11s} {'fuera calend.':>14s} "
          f"{'de esas, vol>0':>15s}")
    for nem, (y, b) in datos.items():
        fuera = y[~y["date"].isin(set(b["date"]))]
        con_vol = int((fuera["y_vol"] > 0).sum())
        print(f"  {nem:10s} {len(y):11d} {len(fuera):14d} {con_vol:15d}")
    print("\n  Nota: la BVL manda como calendario (build_trading_calendar), asi que")
    print("  estas filas se descartan solas en el merge. No contaminan el panel.")

    # ── B y C. ceros contradictorios ────────────────────────────────────────
    print("\n" + "=" * 78)
    print("B/C. DIAS CON volumen=0 PERO PRECIO BVL QUE CAMBIO")
    print("=" * 78)
    for nem, (y, b) in datos.items():
        b = b.copy()
        b["ret"] = b["close"].pct_change()
        m = b.merge(y, on="date", how="inner")
        mal = m[(m["y_vol"] == 0) & (m["ret"].abs() > 0)]
        if mal.empty:
            print(f"\n  {nem}: ninguno")
            continue
        por_anio = mal.groupby(mal["date"].dt.year).size()
        tot = m[m["ret"].abs() > 0]
        pct = 100.0 * len(mal) / len(tot) if len(tot) else 0.0
        med = float(mal["ret"].abs().median()) * 100
        p90 = float(mal["ret"].abs().quantile(0.90)) * 100
        base = float(tot["ret"].abs().median()) * 100
        print(f"\n  {nem}: {len(mal)} dias ({pct:.1f}% de los dias con cambio)")
        print(f"    |ret| mediano en esos dias = {med:.2f}%  (p90 {p90:.2f}%)  "
              f"vs {base:.2f}% en el conjunto")
        print(f"    por año: {dict(por_anio)}")

    # ── D. test economico corregido ─────────────────────────────────────────
    print("\n" + "=" * 78)
    print("D. |RETORNO| vs VOLUMEN, excluyendo retornos exactamente 0")
    print("=" * 78)
    print(f"  {'activo':10s} {'n':>6s} {'spearman':>9s}   "
          f"{'Q1':>11s} {'Q2':>11s} {'Q3':>11s} {'Q4':>11s}  {'Q4/Q1':>6s}")
    for nem, (y, b) in datos.items():
        b = b.copy()
        b["ret"] = b["close"].pct_change()
        m = b.merge(y, on="date", how="inner").dropna(subset=["ret", "y_vol"])
        m = m[(m["ret"].abs() > 0) & (m["y_vol"] > 0)]
        if len(m) < 200:
            continue
        aret = m["ret"].abs()
        rho = float(aret.corr(m["y_vol"], method="spearman"))
        q = pd.qcut(aret, 4, labels=False, duplicates="drop")
        med = m.groupby(q)["y_vol"].median()
        vals = [float(med.get(i, np.nan)) for i in range(4)]
        rat = vals[3] / vals[0] if vals[0] else float("nan")
        print(f"  {nem:10s} {len(m):6d} {rho:9.3f}   "
              + " ".join(f"{v:>10,.0f}" for v in vals) + f"  {rat:6.2f}")
    print("\n  (mediana por cuartil; Q4/Q1 > 1 = el volumen sube con la volatilidad)")
    print("=" * 78)


if __name__ == "__main__":
    main()
