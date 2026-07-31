"""VALIDACION del volumen de Yahoo (.LM) para el universo de la tesis.

Pregunta: el volumen que entrega Yahoo para los tickers de la BVL, es real o
esta inventado/interpolado? La BVL solo publica volumen del ULTIMO dia
(/v1/issuers/{cc}/value -> listLastValue), asi que no hay serie historica que
sirva de contraste. Se valida entonces con UN ancla externa puntual + cinco
pruebas FALSABLES contra los precios de la BVL (2012-2025).

TESTS
  1. ANCLA EXTERNA  : volumen Yahoo vs quantityNegotiated oficial de la BVL en la
                      ultima fecha negociada. Coincidencia exacta = Yahoo replica
                      el dato oficial.
  2. CONTRADICCION  : dias donde el precio BVL CAMBIO pero Yahoo dice volumen=0.
                      Fisicamente imposible: sin operacion no hay precio nuevo.
                      Una tasa alta refuta la fiabilidad.
  3. COMPLEMENTO    : dias con volumen>0 y precio BVL sin cambio. PLAUSIBLE (se
                      opero al mismo precio) y es la informacion que el flag
                      is_stale NO captura.
  4. FUERA DE CALEND: Yahoo con volumen>0 en fechas donde la BVL no cotizo.
                      Sospechoso si es masivo.
  5. ESTRUCTURA     : huella digital de un dato real vs sintetico -- % de
                      volumenes multiplos de 100/1000, repeticiones consecutivas
                      identicas, y ley de Benford sobre el primer digito.
  6. VALIDEZ ECON.  : en mercados reales |retorno| y volumen covarian. Spearman
                      y volumen medio por cuartil de |retorno|. Correlacion ~0
                      sugiere un volumen desconectado del precio (fabricado).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from src.universe import Config

TICKERS = {
    "MINSURI1": "MINSURI1.LM",
    "INRETC1":  "INRETC1.LM",
    "CPACASC1": "CPACASC1.LM",
    "FERREYC1": "FERREYC1.LM",
    "LUSURC1":  "LUSURC1.LM",
    "ALICORC1": "ALICORC1.LM",   # control: ya en uso
    "CREDITC1": "CREDITC1.LM",   # control: ya en uso
}

START, END = "2012-01-01", "2025-12-31"

_DOD = "https://dataondemand.bvl.com.pe"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": "https://www.bvl.com.pe",
    "Referer": "https://www.bvl.com.pe/",
    "Accept": "application/json, text/plain, */*",
}


# ── carga ────────────────────────────────────────────────────────────────────
def yahoo_hist(tk: str, start: str = START, end: str = END) -> pd.DataFrame:
    raw = yf.Ticker(tk).history(start=start, end=end, auto_adjust=False)
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


def bvl_ultimo(cc: str, nem: str) -> dict | None:
    """listLastValue de la BVL: volumen oficial del ultimo dia negociado."""
    try:
        r = requests.get(f"{_DOD}/v1/issuers/{cc}/value", headers=_HEADERS, timeout=25)
        r.raise_for_status()
        for entry in r.json():
            if (entry.get("nemonico") or "").upper() != nem.upper():
                continue
            llv = entry.get("listLastValue") or []
            if llv:
                return llv[0]
    except Exception as exc:
        print(f"    [BVL] {nem}: fallo listLastValue ({exc})")
    return None


# ── tests ────────────────────────────────────────────────────────────────────
def test_ancla(cfg) -> None:
    print("\n" + "=" * 78)
    print("TEST 1 - ANCLA EXTERNA: Yahoo vs quantityNegotiated oficial de la BVL")
    print("=" * 78)
    by_bvl = {a.bvl: a for a in cfg.assets}

    for nem, tk in TICKERS.items():
        asset = by_bvl.get(nem)
        cc = getattr(asset, "bvl_company_code", None) if asset else None
        if not cc:
            print(f"  {nem:10s} sin bvl_company_code en config -> se omite")
            continue

        llv = bvl_ultimo(str(cc), nem)
        if not llv:
            print(f"  {nem:10s} la BVL no devolvio listLastValue")
            continue

        fecha = pd.to_datetime(llv.get("dateTimP"), dayfirst=True).normalize()
        qn = float(llv.get("quantityNegotiated") or 0)
        amount = float(llv.get("amount") or 0)
        close_bvl = float(llv.get("close") or 0)
        buy, sell = llv.get("buy"), llv.get("sell")

        y = yahoo_hist(tk, start=(fecha - pd.Timedelta(days=7)).strftime("%Y-%m-%d"),
                       end=(fecha + pd.Timedelta(days=2)).strftime("%Y-%m-%d"))
        fila = y[y["date"] == fecha] if not y.empty else pd.DataFrame()

        print(f"\n  {nem} ({tk})   fecha BVL = {fecha.date()}")
        print(f"    BVL  : volumen={qn:>14,.0f}  monto={amount:>16,.2f}  "
              f"close={close_bvl:.4f}  punta {buy}/{sell}")
        if fila.empty:
            print(f"    Yahoo: SIN fila en esa fecha -> no comparable")
            continue
        yv = float(fila["y_vol"].iloc[0])
        yc = float(fila["y_close"].iloc[0])
        if qn > 0:
            dif = 100.0 * (yv - qn) / qn
            if abs(dif) < 0.001:
                ver = "IDENTICO -> Yahoo replica el dato oficial de la BVL"
            elif abs(dif) < 5:
                ver = "coincide (<5%)"
            else:
                ver = "DIFIERE"
        else:
            ver = "BVL reporta 0"
        print(f"    Yahoo: volumen={yv:>14,.0f}  close={yc:.4f}   -> {ver}")
        if qn > 0 and amount > 0:
            print(f"    VWAP implicito BVL = {amount / qn:.4f}  (close BVL {close_bvl:.4f})")


def test_consistencia(cfg) -> None:
    print("\n" + "=" * 78)
    print("TESTS 2-4 - CONSISTENCIA con los precios de la BVL (2012-2025)")
    print("=" * 78)
    print(f"  {'activo':10s} {'n_comun':>7s} {'T2 vol=0 & precio':>18s} "
          f"{'T3 vol>0 & sin cambio':>22s} {'T4 yahoo fuera BVL':>19s}")
    print(f"  {'':10s} {'':>7s} {'CAMBIO (imposible)':>18s} {'(info nueva)':>22s} "
          f"{'(con volumen)':>19s}")

    by_bvl = {a.bvl: a for a in cfg.assets}
    for nem, tk in TICKERS.items():
        asset = by_bvl.get(nem)
        if asset is None:
            continue
        y, b = yahoo_hist(tk), bvl_hist(cfg, asset)
        if y.empty or b.empty:
            print(f"  {nem:10s} sin datos")
            continue

        b = b[(b["date"] >= START) & (b["date"] <= END)].copy()
        b["cambio"] = b["close"].diff().fillna(0) != 0

        m = b.merge(y, on="date", how="left")
        comun = m["y_vol"].notna()
        n_comun = int(comun.sum())

        vol0 = comun & (m["y_vol"] == 0)
        t2 = int((vol0 & m["cambio"]).sum())
        n_cambio = int((m["cambio"] & comun).sum())
        t3 = int((comun & (m["y_vol"] > 0) & ~m["cambio"]).sum())
        n_sincambio = int((~m["cambio"] & comun).sum())

        fuera = y[~y["date"].isin(set(b["date"]))]
        t4 = int((fuera["y_vol"] > 0).sum())

        p2 = 100.0 * t2 / n_cambio if n_cambio else 0.0
        p3 = 100.0 * t3 / n_sincambio if n_sincambio else 0.0
        print(f"  {nem:10s} {n_comun:7d} {t2:8d} ({p2:5.2f}%) "
              f"{t3:12d} ({p3:5.1f}%) {t4:12d} / {len(fuera):d}")


def test_estructura() -> None:
    print("\n" + "=" * 78)
    print("TEST 5 - ESTRUCTURA (huella de dato real vs sintetico)")
    print("=" * 78)
    # Benford esperado para el primer digito
    benford = {d: math.log10(1 + 1 / d) for d in range(1, 10)}

    print(f"  {'activo':10s} {'n>0':>6s} {'%x100':>7s} {'%x1000':>7s} "
          f"{'%repet':>7s} {'run_max':>8s} {'MAD_Benford':>12s}  veredicto")
    for nem, tk in TICKERS.items():
        y = yahoo_hist(tk)
        if y.empty:
            continue
        v = y["y_vol"].dropna()
        v = v[v > 0].astype("int64")
        if v.empty:
            continue

        pct100 = 100.0 * (v % 100 == 0).mean()
        pct1000 = 100.0 * (v % 1000 == 0).mean()

        # repeticiones consecutivas identicas (senal de relleno/ffill)
        rep = (v.reset_index(drop=True).diff() == 0)
        pct_rep = 100.0 * rep.mean()
        run, run_max = 0, 0
        for flag in rep:
            run = run + 1 if flag else 0
            run_max = max(run_max, run)

        # Benford: desviacion absoluta media sobre el primer digito
        first = v.astype(str).str[0].astype(int)
        obs = first.value_counts(normalize=True)
        mad = float(np.mean([abs(obs.get(d, 0.0) - benford[d]) for d in range(1, 10)]))

        if mad < 0.006:
            ver = "conforme a Benford (dato natural)"
        elif mad < 0.012:
            ver = "aceptable"
        elif mad < 0.015:
            ver = "marginal"
        else:
            ver = "NO conforme -> revisar"

        print(f"  {nem:10s} {len(v):6d} {pct100:7.1f} {pct1000:7.1f} "
              f"{pct_rep:7.2f} {run_max:8d} {mad:12.4f}  {ver}")


def test_economico(cfg) -> None:
    print("\n" + "=" * 78)
    print("TEST 6 - VALIDEZ ECONOMICA: |retorno| vs volumen")
    print("=" * 78)
    print("  (en mercados reales el volumen sube con la magnitud del movimiento)")
    print(f"\n  {'activo':10s} {'spearman':>9s}  {'vol.medio por cuartil de |ret|':>44s}")
    print(f"  {'':10s} {'':>9s}  {'Q1(quieto)':>12s} {'Q2':>10s} {'Q3':>10s} {'Q4(volatil)':>12s}")

    by_bvl = {a.bvl: a for a in cfg.assets}
    for nem, tk in TICKERS.items():
        asset = by_bvl.get(nem)
        if asset is None:
            continue
        y, b = yahoo_hist(tk), bvl_hist(cfg, asset)
        if y.empty or b.empty:
            continue

        m = b.merge(y, on="date", how="inner").sort_values("date")
        m["ret"] = m["close"].pct_change()
        m = m.dropna(subset=["ret", "y_vol"])
        m = m[m["y_vol"] > 0]
        if len(m) < 100:
            continue

        aret = m["ret"].abs()
        rho = float(aret.corr(m["y_vol"], method="spearman"))
        try:
            q = pd.qcut(aret, 4, labels=False, duplicates="drop")
            medias = m.groupby(q)["y_vol"].mean()
        except Exception:
            continue

        vals = [medias.get(i, float("nan")) for i in range(4)]
        print(f"  {nem:10s} {rho:9.3f}  " + " ".join(f"{v:>11,.0f}" for v in vals))


def main() -> None:
    cfg = Config.load("config.yaml")
    test_ancla(cfg)
    test_consistencia(cfg)
    test_estructura()
    test_economico(cfg)
    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
