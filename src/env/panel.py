"""OE1 — carga del panel y arrays que consume el entorno.

Separa "leer el parquet de R6" de "simular": el entorno no toca pandas, solo
arrays. Eso lo hace rápido, testeable y trivial de sustituir por datos
sintéticos en las pruebas.

GUARDAS QUE FALLAN TEMPRANO (ver memoria `feedback-deriva-decidido-implementado`):
el panel tiene que ser rectangular, sin huecos de precio y con todas las
columnas de control. Si algo falta, se cae acá y no diez pasos después con un
NaN silencioso dentro de la recompensa.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .features import FeatureTensor, build_features

#: Columna de valuación. Es retorno TOTAL: ya incluye dividendos reinvertidos,
#: que es lo económicamente correcto para un portafolio (D4).
PRICE_COL = "close_total_return"

#: Tasa de referencia del BCRP, en porcentaje anual (p.ej. 4.25). D9.
RF_COL = "macro_tasa_ref"

DEFAULT_PANEL = Path("data/processed/dataset_unificado.parquet")


@dataclass
class PanelData:
    """Todo lo que el entorno necesita, ya en arrays alineados por fecha."""

    dates: np.ndarray  # (T,) datetime64
    tickers: list[str]
    prices: np.ndarray  # (T, n) valuación total-return
    no_trade: np.ndarray  # (T, n) bool — restricción dura (D8)
    stale: np.ndarray  # (T, n) bool — recargo de costo, no prohibición (D8)
    rf_daily: np.ndarray  # (T,) tasa libre de riesgo diaria (D9)
    features: FeatureTensor
    #: Primer índice en el que TODOS los activos ya cotizan. Antes de esa fecha
    #: el universo no está completo (InRetail sale a bolsa en 2012-10) y el
    #: entorno no puede arrancar: no se puede tener lo que no está listado.
    first_tradable_index: int = 0

    @property
    def n_steps(self) -> int:
        return len(self.dates)

    @property
    def n_assets(self) -> int:
        return len(self.tickers)


def load_panel(
    path: str | Path = DEFAULT_PANEL,
    tickers: list[str] | None = None,
    view: str = "completa",
    start: str | None = None,
    end: str | None = None,
    warmup: int = 250,
) -> PanelData:
    """Lee el panel de R6 y lo convierte en arrays para el entorno.

    Args:
        path: parquet de `build_dataset` (R6).
        tickers: subconjunto y orden canónico. Por defecto, todos, ordenados.
        view: vista de señales (ver `features.VIEWS`).
        start, end: recorte temporal, inclusivo. Es como se arman los pliegues
            del walk-forward de D10.
        warmup: días de calentamiento de la normalización causal (D6).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"no existe {path}. Corre R6 (build_dataset) antes de usar el entorno."
        )
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])

    if tickers is None:
        tickers = sorted(df["ticker"].unique().tolist())
    faltan = sorted(set(tickers) - set(df["ticker"].unique()))
    if faltan:
        raise KeyError(f"el panel no tiene {faltan}")
    df = df[df["ticker"].isin(tickers)]

    if start is not None:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["date"] <= pd.Timestamp(end)]
    df = df.sort_values(["date", "ticker"]).reset_index(drop=True)

    for col in (PRICE_COL, RF_COL, "is_no_trade", "is_stale"):
        if col not in df.columns:
            raise KeyError(f"el panel no trae la columna requerida {col!r}")

    dates = np.sort(df["date"].unique())
    esperado = len(dates) * len(tickers)
    if len(df) != esperado:
        raise ValueError(
            f"el panel no es rectangular: {len(df)} filas para {len(dates)} fechas "
            f"x {len(tickers)} activos ({esperado}). R6 debe entregarlo balanceado."
        )

    def _wide(col: str) -> np.ndarray:
        return (
            df.pivot(index="date", columns="ticker", values=col)
            .reindex(index=dates, columns=tickers)
            .to_numpy(dtype=float)
            .copy()  # pandas puede devolver una vista de solo lectura
        )

    prices = _wide(PRICE_COL)
    no_trade = _wide("is_no_trade") > 0.5

    # --- activos que todavía no cotizan (InRetail sale a bolsa en 2012-10) ---
    # NO es un hueco de datos: es que el valor no existía. Se distingue un
    # bloque INICIAL sin precio (aceptable, el entorno no puede arrancar ahí) de
    # un hueco POSTERIOR (eso sí es un error de R6 y hay que caerse).
    validos = np.isfinite(prices)
    if not validos.any(axis=0).all():
        muertos = [t for t, v in zip(tickers, validos.any(axis=0)) if not v]
        raise ValueError(f"sin ningún precio en el tramo pedido: {muertos}")
    primer_valido = validos.argmax(axis=0)
    first_tradable = int(primer_valido.max())
    if not validos[first_tradable:].all():
        faltan = [
            tickers[j]
            for j in range(len(tickers))
            if not validos[first_tradable:, j].all()
        ]
        raise ValueError(
            f"{PRICE_COL} tiene huecos DESPUÉS de {dates[first_tradable]} en {faltan}; "
            "eso es un problema de R6, no una salida a bolsa tardía"
        )
    if first_tradable > 0:
        # Relleno no informativo de las filas previas, que el entorno nunca
        # alcanza: se marcan además como no operables, por si alguien mueve t0.
        for j, i0 in enumerate(primer_valido):
            prices[:i0, j] = prices[i0, j]
            no_trade[:i0, j] = True
    if np.any(prices <= 0):
        raise ValueError(f"{PRICE_COL} tiene valores no positivos")

    rf_annual_pct = df.groupby("date")[RF_COL].first().reindex(dates).to_numpy(dtype=float)
    if not np.all(np.isfinite(rf_annual_pct)):
        raise ValueError(f"{RF_COL} tiene huecos; la caja no se puede remunerar (D9)")
    # D9: "la tasa del banco central, que cambia cada mes, dividida entre 365".
    rf_daily = rf_annual_pct / 100.0 / 365.0

    features = build_features(df, tickers=tickers, view=view, warmup=warmup)
    if features.values.shape[0] != len(dates):
        raise ValueError("el tensor de features no quedó alineado con el calendario")

    return PanelData(
        dates=dates,
        tickers=list(tickers),
        prices=prices,
        no_trade=no_trade,
        stale=_wide("is_stale") > 0.5,
        rf_daily=rf_daily,
        features=features,
        first_tradable_index=first_tradable,
    )
