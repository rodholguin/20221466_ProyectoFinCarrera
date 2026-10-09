"""Tests del paso a estados CONSOLIDADOS en R4 (2026-10-09).

Tres reglas, cada una con el caso real que la motivó:
  1. En el consolidado, EPS y ROE usan la utilidad ATRIBUIBLE a la controladora
     (2D0802) y no la del grupo (MINSURI1 2023: +44% por el minoritario de
     Marcobre). Margen y ROA siguen con las cifras del grupo.
  2. Una tesorería con signo positivo no es tesorería (CPACASC1 2012Q1-Q2).
  3. La fecha real del individual es piso del fallback del consolidado
     (LUSURC1 2020Q1: 68 días de look-ahead sin el piso).

    python -m pytest tests/test_fundamentales_consolidado.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.fundamentals.fundamentals_client import (
    _known_date, compute_ratios, compute_shares_earnings,
)

PERIODOS = ["2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31"]


def _activo():
    return SimpleNamespace(bvl="TESTC1", nominal_value=1.0,
                           shares_outstanding_override=None,
                           shares_outstanding_schedule=None)


def _largo(cuentas: dict[str, list[float]]) -> pd.DataFrame:
    """Formato FUNDAMENTALS_SCHEMA con un valor por cuenta y periodo."""
    filas = []
    for cuenta, valores in cuentas.items():
        for periodo, valor in zip(PERIODOS, valores):
            filas.append({"ticker": "TESTC1", "period": periodo,
                          "known_date": periodo, "known_date_real": 0,
                          "account": cuenta, "value": float(valor),
                          "currency": "PEN", "source": "smv"})
    return pd.DataFrame(filas)


# Grupo: utilidad trimestral 150 (100 de la controladora + 50 de minoritarios).
BASE = {
    "INFO_UtilidadNeta":    [150, 150, 150, 150],
    "INFO_PatrimonioTotal": [3000] * 4,
    "INFO_ActivoTotal":     [6000] * 4,
    "INFO_TotalIngreso":    [1500] * 4,
    "INFO_PasivoTotal":     [3000] * 4,
    "GP_Q_2D07ST":          [150, 150, 150, 150],
    "GP_2D07ST":            [150, 300, 450, 600],
    "BG_1D0701":            [1000] * 4,
    "BG_1D0711":            [0] * 4,
}
ATRIBUIBLE = {
    "GP_Q_2D0802": [100, 100, 100, 100],
    "GP_2D0802":   [100, 200, 300, 400],
    "BG_1D0710":   [2000] * 4,
}


def test_consolidado_eps_usa_la_utilidad_atribuible():
    se = compute_shares_earnings(_largo(BASE | ATRIBUIBLE), _activo())
    ultimo = se.iloc[-1]
    assert ultimo["net_income_ttm"] == 400.0           # no 600 (la del grupo)
    assert abs(ultimo["eps_ttm"] - 0.4) < 1e-12        # 400 mil / 1 millón


def test_individual_sin_apertura_queda_igual():
    se = compute_shares_earnings(_largo(BASE), _activo())
    assert se.iloc[-1]["net_income_ttm"] == 600.0


def test_consolidado_roe_atribuible_y_margen_del_grupo():
    r = compute_ratios(_largo(BASE | ATRIBUIBLE)).iloc[-1]
    assert abs(r["roe"] - 100 / 2000) < 1e-12          # par atribuible
    assert abs(r["net_margin"] - 150 / 1500) < 1e-12   # grupo / ingresos del grupo
    assert abs(r["roa"] - 150 / 6000) < 1e-12


def test_roe_no_mezcla_utilidad_atribuible_con_patrimonio_total():
    sin_patrimonio = {k: v for k, v in ATRIBUIBLE.items() if k != "BG_1D0710"}
    r = compute_ratios(_largo(BASE | sin_patrimonio)).iloc[-1]
    assert abs(r["roe"] - 150 / 3000) < 1e-12          # cae al par total, entero


def test_tesoreria_positiva_se_descarta():
    cuentas = BASE | {"BG_1D0711": [0, 1500, -100, 0]}  # +1500 > capital: no es tesorería
    se = compute_shares_earnings(_largo(cuentas), _activo()).set_index("period")
    assert se.loc["2023-06-30", "shares_outstanding"] == 1_000_000
    assert se.loc["2023-09-30", "shares_outstanding"] == 900_000   # la negativa sí resta


def test_fecha_del_individual_es_piso_del_fallback():
    lags = {1: 55, 2: 55, 3: 55, 4: 68}
    piso = {(2020, 1): date(2020, 8, 1)}
    fecha, real = _known_date(2020, 1, {}, lags, piso)
    assert fecha == date(2020, 8, 1) and real is False
    # Sin piso, el lag; y la fecha real del consolidado siempre manda.
    assert _known_date(2020, 1, {}, lags)[0] == date(2020, 5, 25)
    assert _known_date(2020, 1, {(2020, 1): date(2020, 8, 14)}, lags, piso) == \
        (date(2020, 8, 14), True)
