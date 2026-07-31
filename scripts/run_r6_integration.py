"""R6 — Construcción del dataset unificado.

Lee mercado (interim), sentimiento (interim) y fundamentales crudos (raw, vía
compute_ratios) de los activos de config.yaml, les suma los features macro
globales del BCRP (src.macro.macro_client, alineados point-in-time sobre el
calendario bursátil) y arma el panel único (ticker, date) en
data/processed/dataset_unificado.parquet.

Uso:
  python scripts/run_r6_integration.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.universe import Config
from src.fundamentals.fundamentals_client import compute_ratios
from src.macro.macro_client import macro_features
from src.market.corporate_actions import fetch_actions, filter_actions_by_cutoff
from src.integration.build_dataset import (
    build_trading_calendar, build_unified, feature_views, save,
)


def _dividends_frame(asset, end: str, market_dates: pd.Series) -> pd.DataFrame:
    """Serie de dividendos por acción en PEN (misma fuente autoritativa de R3:
    BVL /value, US$->PEN con TC BCRP) para el DY. Devuelve [ticker, date, dividend]
    con fecha = fecha de corte (~ex-date). Recortada al horizonte con el mismo
    filtro por cutoff que usa el pipeline de mercado."""
    try:
        actions = filter_actions_by_cutoff(fetch_actions(asset), end, market_dates)
    except Exception as exc:
        print(f"  AVISO: dividendos {asset.bvl} no disponibles ({exc}); DY = NaN.")
        return pd.DataFrame(columns=["ticker", "date", "dividend"])
    div = actions["dividends"]
    return pd.DataFrame({"ticker": asset.bvl,
                         "date": pd.DatetimeIndex(div.index),
                         "dividend": div.to_numpy()})


def main() -> None:
    cfg = Config.load(ROOT / "config.yaml")
    interim_dir = ROOT / cfg.paths["interim"]
    raw_dir = ROOT / cfg.paths["raw"]
    processed_dir = ROOT / cfg.paths["processed"]

    market_frames, sentiment_frames, ratio_frames, div_frames = [], [], [], []
    for asset in cfg.assets:
        ticker = asset.bvl

        mkt_path = interim_dir / f"market_{ticker}.parquet"
        if mkt_path.exists():
            mkt = pd.read_parquet(mkt_path)
            market_frames.append(mkt)
            # DY: dividendos por acción (PEN) desde la capa de acciones corporativas
            div_frames.append(_dividends_frame(asset, cfg.end, mkt["date"]))
        else:
            print(f"  AVISO: falta {mkt_path.name}, {ticker} sin mercado.")

        sent_path = interim_dir / f"sentiment_{ticker}.parquet"
        if sent_path.exists():
            sentiment_frames.append(pd.read_parquet(sent_path))
        else:
            print(f"  AVISO: falta {sent_path.name}, {ticker} sin sentimiento.")

        fund_path = raw_dir / f"fund_{ticker}_smv.parquet"
        if fund_path.exists():
            ratio_frames.append(compute_ratios(pd.read_parquet(fund_path), asset=asset))
        else:
            print(f"  AVISO: falta {fund_path.name}, {ticker} sin fundamentales.")

    market = pd.concat(market_frames, ignore_index=True)
    sentiment = (pd.concat(sentiment_frames, ignore_index=True) if sentiment_frames
                 else pd.DataFrame(columns=["ticker", "date", "sentiment_score",
                                            "n_articles", "source"]))
    ratios = (pd.concat(ratio_frames, ignore_index=True) if ratio_frames
              else pd.DataFrame(columns=["ticker", "period", "known_date", "currency",
                                         "roe", "roa", "net_margin", "debt_equity",
                                         "debt_ratio"]))
    dividends = (pd.concat(div_frames, ignore_index=True) if div_frames else None)

    print(f"Mercado:      {len(market):>6} filas, {market['ticker'].nunique()} activos")
    print(f"Sentimiento:  {len(sentiment):>6} filas, {sentiment['ticker'].nunique()} activos")
    print(f"Fundamentales:{len(ratios):>6} filas, {ratios['ticker'].nunique()} activos")

    # Macro (BCRP, 6 series globales): se resuelve AQUÍ sobre el calendario
    # bursátil del panel y se pasa ya alineado point-in-time (niveles crudos; la
    # transformación —retorno log en precios, nivel+cambio en tasa/EMBI— es de OE1).
    calendar = build_trading_calendar(market)
    try:
        macro = macro_features(calendar)
        print(f"Macro:        {len(macro):>6} fechas, {len(macro.columns)} series "
              f"({', '.join(macro.columns)})")
        nan_macro = macro.isna().sum()
        if nan_macro.any():
            print(f"  AVISO: NaN en macro (fechas previas al 1er dato de la serie): "
                  f"{nan_macro[nan_macro > 0].to_dict()}")
    except Exception as exc:
        print(f"  AVISO: features macro no disponibles ({exc}); panel SIN columnas macro.")
        macro = None

    unified = build_unified(market, sentiment, ratios, dividends=dividends,
                            trading_calendar=calendar, macro=macro)

    print(f"\nPanel unificado: {len(unified)} filas x {len(unified.columns)} columnas")
    print(f"Rango: {unified['date'].min().date()} -> {unified['date'].max().date()}")
    print(f"Columnas: {list(unified.columns)}")

    out = save(unified, processed_dir)
    print(f"\nGuardado en {out}")

    print("\nVistas de señales (R8):")
    for name, cols in feature_views(unified).items():
        print(f"  {name}: {cols}")


if __name__ == "__main__":
    main()
