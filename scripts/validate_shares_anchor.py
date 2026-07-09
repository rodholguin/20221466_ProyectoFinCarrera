"""Validacion del ancla de acciones en circulacion (jul-2026).

Contrasta DOS fuentes/metodos para el numero de acciones historico, tras confirmar
que la BVL expone el ancla actual (listStock.quantity en /v1/issuers/{cc}/value):

  A) SMV Capital Emitido / valor nominal  -> serie HISTORICA trimestral directa
     (ya descargada en data/raw/smv_cache; captura splits Y aumentos/reducciones
     de capital). Cuenta 1D0701 (no bancos) o 1F3301 "Capital social" (BCP).
  B) Ancla BVL actual / factor acumulado de splits (corporate_actions.py)
     -> reconstruccion que SOLO captura acciones liberadas (AL), no aportes ni
     reducciones de capital.

Objetivo: medir el error de (B) frente a (A), y confirmar que (A) coincide con el
ancla BVL en el extremo reciente. Decidir con datos cual usar para P/E y DY.
"""
from __future__ import annotations

import glob
import json
import os

import pandas as pd

from src.market.corporate_actions import (
    align_splits_to_price, fetch_actions, split_factor,
)
from src.universe import Config

# Ancla BVL (snapshot 2026-07-06) y cuenta de capital por activo -------------
BVL_ANCHOR = {  # nemonico -> (quantity, nominalValue, cuenta_capital, moneda_smv)
    "CREDITC1": (12973174634, 1,  "1F3301", "PEN"),
    "BUENAVC1": (274889924,   10, "1D0701", "USD"),
    "ALICORC1": (569573006,   1,  "1D0701", "PEN"),
    "SAGAC1":   (156709425,   1,  "1D0701", "PEN"),
    "CORAREC1": (890858308,   1,  "1D0701", "PEN"),
}
RPJ = {"CREDITC1": "B80005", "BUENAVC1": "B20003", "ALICORC1": "B30006",
       "SAGAC1": "014313", "CORAREC1": "CI0003"}

CACHE = r"C:\tesis\data\raw\smv_cache"
Q_END = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def smv_capital_series(rpj: str, cuenta: str) -> pd.Series:
    """Serie trimestral de Capital Emitido (Monto1, en miles) desde el cache SMV."""
    out = {}
    for f in sorted(glob.glob(os.path.join(CACHE, "obtener_BalanceGeneral_*_I.json"))):
        base = os.path.basename(f)
        # obtener_BalanceGeneral_2012Q3_I.json
        tag = base.split("_")[2]          # 2012Q3
        year, q = int(tag[:4]), int(tag[5])
        d = json.load(open(f, encoding="utf-8"))
        for r in d:
            if r.get("RPJ") == rpj and r.get("Cuenta") == cuenta:
                val = r.get("Monto1")
                if val not in (None, ""):
                    out[pd.Timestamp(f"{year}-{Q_END[q]}")] = float(val)
                break
    return pd.Series(out).sort_index()


def main():
    cfg = Config.load()
    assets = {a.bvl: a for a in cfg.assets}

    for nemo, (qty, nominal, cuenta, moneda) in BVL_ANCHOR.items():
        print(f"\n{'='*74}\n{nemo}  (ancla BVL quantity={qty:,}  nominal={nominal}  "
              f"cuenta={cuenta}  moneda_smv={moneda})")

        # --- A) serie SMV Capital Emitido / nominal -> acciones -------------
        cap = smv_capital_series(RPJ[nemo], cuenta)   # miles de la moneda
        shares_smv = cap * 1000.0 / nominal
        if shares_smv.empty:
            print("  (sin Capital Emitido en cache SMV)")
            continue

        # --- B) reconstruccion por factor de splits desde el ancla ---------
        asset = assets[nemo]
        actions = fetch_actions(asset)
        mkt = pd.read_parquet(rf"C:\tesis\data\raw\market_{nemo}_bvl.parquet")
        close = pd.Series(mkt["close"].to_numpy(),
                          index=pd.DatetimeIndex(mkt["date"])).sort_index()
        splits = align_splits_to_price(close, actions["splits"])
        # factor(fecha) >= 1 (producto de splits posteriores). shares_hist =
        # qty_actual / factor (menos acciones en el pasado, antes de los AL).
        idx = pd.DatetimeIndex(shares_smv.index)
        factor = split_factor(idx, splits)
        shares_recon = pd.Series(qty / factor.to_numpy(), index=idx)

        # --- comparacion en puntos clave -----------------------------------
        comp = pd.DataFrame({"smv_capital/nom": shares_smv,
                             "recon_split": shares_recon})
        comp["dif_%"] = (comp["recon_split"] / comp["smv_capital/nom"] - 1) * 100
        # mostrar primer, ultimo, y donde |dif|>2%
        show = comp.iloc[[0, len(comp)//2, -1]]
        print(show.to_string(float_format=lambda x: f"{x:,.0f}" if abs(x) > 1000 else f"{x:6.2f}"))
        big = comp[comp["dif_%"].abs() > 2.0]
        print(f"  trimestres con |dif|>2%: {len(big)}/{len(comp)}  "
              f"(dif max {comp['dif_%'].abs().max():.1f}%)")
        print(f"  ancla BVL vs SMV ultimo trimestre: "
              f"{qty:,} vs {shares_smv.iloc[-1]:,.0f}  "
              f"(dif {qty/shares_smv.iloc[-1]-1:+.3%})")

        # --- C) yfinance shares (ruido/cobertura, referencia) --------------
        try:
            import yfinance as yf
            if asset.yahoo:
                sf = yf.Ticker(asset.yahoo).get_shares_full(start="2012-01-01")
                if sf is not None and len(sf):
                    sf = sf[~sf.index.duplicated(keep="last")]
                    print(f"  yfinance shares: n={len(sf)}  rango "
                          f"{sf.index.min().date()}..{sf.index.max().date()}  "
                          f"ultimo={sf.iloc[-1]:,.0f}")
                else:
                    print("  yfinance shares: vacio")
        except Exception as exc:
            print(f"  yfinance shares: err {exc}")


if __name__ == "__main__":
    main()
