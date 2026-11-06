# -*- coding: utf-8 -*-
"""El costo con el spread OBSERVADO de Bloomberg (2026-10-29).

El snapshot del 2026-07-27 subestimaba ~10x el spread de Alicorp, InRetail y
Minsur. Lo que hay que blindar al pasar a la serie diaria es la ALINEACIÓN: un
spread corrido un día, o un hueco rellenado con cero, cobraría un costo que no
existió sin que nada falle.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.env.costs import LIQUIDEZ_BLOOMBERG, CostModel, serie_spread_bps  # noqa: E402


def _volcado(tmp_path, filas) -> Path:
    df = pd.DataFrame(filas, columns=["date", "ticker", "spread_bps"])
    df["date"] = pd.to_datetime(df["date"])
    ruta = tmp_path / "liq.parquet"
    df.to_parquet(ruta, index=False)
    return ruta


def test_cada_dia_cobra_su_propio_spread(tmp_path):
    ruta = _volcado(tmp_path, [
        ("2024-01-02", "A", 100.0), ("2024-01-03", "A", 200.0), ("2024-01-04", "A", 300.0),
        ("2024-01-02", "B", 10.0), ("2024-01-03", "B", 20.0), ("2024-01-04", "B", 30.0),
    ])
    fechas = np.array(["2024-01-02", "2024-01-03", "2024-01-04"], dtype="datetime64[D]")
    s = serie_spread_bps(["B", "A"], fechas, ruta)  # el orden lo pone el panel
    assert s.tolist() == [[10.0, 100.0], [20.0, 200.0], [30.0, 300.0]]

    cm = CostModel(tickers=["B", "A"], half_spread_bps=s / 2.0, commission_rate=0.0,
                   min_fee=0.0, igv=0.0, fees_rate=0.0)
    # Medio spread por lado: 1 millón en A el día 1 cuesta 100 pbs / 2 = S/10,000.
    assert cm.cost_of_trades(np.array([0.0, 1e6]), 1).sum() == pytest.approx(10_000.0)


def test_dia_sin_dato_hereda_el_ultimo_spread_y_no_cero(tmp_path):
    ruta = _volcado(tmp_path, [
        ("2024-01-02", "A", 100.0), ("2024-01-03", "A", np.nan), ("2024-01-04", "A", 300.0),
    ])
    fechas = np.array(["2024-01-02", "2024-01-03", "2024-01-04"], dtype="datetime64[D]")
    assert serie_spread_bps(["A"], fechas, ruta)[:, 0].tolist() == [100.0, 100.0, 300.0]


def test_feriado_que_no_coincide_no_deja_hueco(tmp_path):
    # Bloomberg no trae el 2024-01-03, pero el panel sí lo tiene: hereda el 02.
    ruta = _volcado(tmp_path, [("2024-01-02", "A", 100.0), ("2024-01-04", "A", 300.0)])
    fechas = np.array(["2024-01-02", "2024-01-03", "2024-01-04"], dtype="datetime64[D]")
    assert serie_spread_bps(["A"], fechas, ruta)[:, 0].tolist() == [100.0, 100.0, 300.0]


def test_sin_dato_en_el_tramo_operable_se_cae(tmp_path):
    ruta = _volcado(tmp_path, [("2024-01-04", "A", 300.0)])
    fechas = np.array(["2024-01-02", "2024-01-03", "2024-01-04"], dtype="datetime64[D]")
    with pytest.raises(ValueError, match="huecos"):
        serie_spread_bps(["A"], fechas, ruta, desde_indice=1)
    # Antes del tramo operable (calentamiento) se acepta con el primer dato.
    assert serie_spread_bps(["A"], fechas, ruta, desde_indice=2)[:, 0].tolist() == [300.0] * 3


def test_activo_sin_serie_se_cae(tmp_path):
    ruta = _volcado(tmp_path, [("2024-01-02", "A", 100.0)])
    with pytest.raises(KeyError, match="B"):
        serie_spread_bps(["A", "B"], np.array(["2024-01-02"], dtype="datetime64[D]"), ruta)


def test_serie_real_si_existe():
    if not LIQUIDEZ_BLOOMBERG.exists():
        pytest.skip("sin el volcado de Bloomberg (licencia: no va a git)")
    from src.env import costos_observados, load_panel

    panel = load_panel(view="solo_mercado", warmup=250)
    cm = costos_observados(panel)
    spread = cm._spread[panel.first_tradable_index:] * 2  # ida y vuelta, pbs
    assert np.isfinite(spread).all() and (spread > 0).all()
    med = dict(zip(panel.tickers, np.median(spread, axis=0)))
    # Guarda contra volver al snapshot: Alicorp, InRetail y Minsur cotizaban
    # 8/13/14 pbs en él; la mediana observada 2013-2025 es de ~60-200.
    for t in ("ALICORC1", "INRETC1", "MINSURI1"):
        assert med[t] > 50, f"{t}: {med[t]:.0f} pbs parece el snapshot, no la serie"
