"""R6 — Integración temporal y dataset unificado.

Une mercado+técnicos (diario) ⨝ sentimiento (diario) ⨝ fundamentales
(trimestral, con forward-fill desde la fecha en que se conocieron) sobre el
calendario de días hábiles de la BVL.

Las 4 "vistas" de señales que pide R8 (solo mercado; +sentimiento;
+fundamentales; completa) NO son datasets separados: son selecciones de
columnas sobre este panel único.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_unified(market: pd.DataFrame, sentiment: pd.DataFrame,
                  fundamentals_ratios: pd.DataFrame,
                  trading_calendar: pd.DatetimeIndex) -> pd.DataFrame:
    """Construye el panel (ticker, date) x features.

    Parameters
    ----------
    market : con OHLCV + indicadores técnicos (diario)
    sentiment : score diario por activo (0/neutral donde no hay noticias)
    fundamentals_ratios : P/E, ROE, DY por (ticker, known_date) trimestral
    trading_calendar : índice de días hábiles de la BVL (feriados PE incluidos)
    """
    panels = []
    for ticker, mkt in market.groupby("ticker"):
        idx = pd.MultiIndex.from_product(
            [[ticker], trading_calendar], names=["ticker", "date"])
        base = pd.DataFrame(index=idx).reset_index()

        mkt = mkt.copy()
        mkt["date"] = pd.to_datetime(mkt["date"])
        panel = base.merge(mkt, on=["ticker", "date"], how="left")

        # Sentimiento: 0 (neutral) los días sin noticias
        sen = sentiment[sentiment["ticker"] == ticker].copy()
        if not sen.empty:
            sen["date"] = pd.to_datetime(sen["date"])
            panel = panel.merge(
                sen[["date", "sentiment_score", "n_articles"]],
                on="date", how="left")
        if "sentiment_score" not in panel.columns:
            panel["sentiment_score"] = 0.0
        if "n_articles" not in panel.columns:
            panel["n_articles"] = 0
        panel["sentiment_score"] = panel["sentiment_score"].fillna(0.0)
        panel["n_articles"] = panel["n_articles"].fillna(0)

        # Fundamentales: forward-fill desde known_date (evita look-ahead)
        fnd = fundamentals_ratios[fundamentals_ratios["ticker"] == ticker].copy()
        if not fnd.empty:
            fnd["known_date"] = pd.to_datetime(fnd["known_date"])
            fnd = fnd.sort_values("known_date")
            panel = pd.merge_asof(
                panel.sort_values("date"), fnd.sort_values("known_date"),
                left_on="date", right_on="known_date", by="ticker",
                direction="backward")

        panels.append(panel)

    unified = pd.concat(panels, ignore_index=True)
    return unified.sort_values(["ticker", "date"]).reset_index(drop=True)


def feature_views(unified: pd.DataFrame) -> dict[str, list[str]]:
    """Devuelve las columnas de cada configuración de señales de R8."""
    technical = [c for c in unified.columns
                 if c in {"open", "high", "low", "close", "volume", "ret_1d",
                          "sma_20", "sma_50", "ema_12", "ema_26", "macd",
                          "macd_signal", "rsi_14", "volatility_20"}]
    sentiment = ["sentiment_score", "n_articles"]
    _fundamental_cols = {
        "roe", "roa", "net_margin", "debt_equity", "debt_ratio",  # derivados SMV
        "pe", "dy",                                                # reservados (P/E, DY futuro)
    }
    fundamental = [c for c in unified.columns if c in _fundamental_cols]
    return {
        "solo_mercado":          technical,
        "mercado_sentimiento":   technical + sentiment,
        "mercado_fundamentales": technical + fundamental,
        "completa":              technical + sentiment + fundamental,
    }


def save(unified: pd.DataFrame, processed_dir: str | Path) -> Path:
    out = Path(processed_dir) / "dataset_unificado.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    unified.to_parquet(out)
    return out
