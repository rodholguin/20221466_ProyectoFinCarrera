"""R3 (tarea 2.2) — Indicadores técnicos sobre el OHLCV canónico.

Se calculan por ticker tras consolidar el precio. Se mantienen en un módulo
aparte para poder activar/desactivar el bloque "solo mercado" frente a las
configuraciones de señales de R8.

Se calculan sobre close_total_return (ajustado por splits y dividendos
reinvertidos) en lugar del close as-traded: es la serie que ve el agente DRL,
libre de los saltos artificiales que introducen los splits/acciones liberadas
sobre el precio crudo (ver corporate_actions.py). ret_1d_raw se conserva sobre
close_raw para análisis de liquidez/contexto que sí requieran el precio
efectivamente negociado.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega indicadores técnicos básicos sobre close_total_return. Espera
    columnas open/high/low/close/volume/close_raw/close_total_return
    ordenadas por fecha para un único ticker."""
    out = df.sort_values("date").copy()
    c = out["close_total_return"]

    out["ret_1d"] = c.pct_change()
    out["ret_1d_raw"] = out["close_raw"].pct_change()
    out["sma_20"] = c.rolling(20).mean()
    out["sma_50"] = c.rolling(50).mean()
    out["ema_12"] = c.ewm(span=12, adjust=False).mean()
    out["ema_26"] = c.ewm(span=26, adjust=False).mean()
    out["macd"] = out["ema_12"] - out["ema_26"]
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["rsi_14"] = _rsi(c, 14)
    out["volatility_20"] = out["ret_1d"].rolling(20).std() * np.sqrt(252)
    return out


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """RSI de Wilder. Cuando la ventana de `window` días no tuvo NINGUNA
    pérdida, RS = ganancia/0 -> el límite de la fórmula es RSI=100 (no es
    una suposición, es el valor de la fórmula estándar, igual que TA-Lib/
    pandas-ta). Si además tampoco hubo ninguna ganancia (ventana
    totalmente plana, 0/0 verdaderamente indefinido -- típico en tramos de
    iliquidez, ver `is_no_trade` en build_dataset.py) se usa la convención
    RSI=50 (sin señal de momentum) en vez de 100, porque ahí no hubo
    movimiento real que justifique "fuerza alcista"."""
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    no_loss = loss == 0   # False para NaN (warm-up): esos quedan intactos
    rsi = rsi.where(~no_loss, np.where(gain > 0, 100.0, 50.0))
    return rsi
