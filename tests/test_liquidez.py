# -*- coding: utf-8 -*-
"""Tope de participación, orden pendiente e impacto de mercado (2026-11-05).

Hasta acá el simulador ejecutaba cualquier orden en el día con solo el medio
spread: la compra inicial de BCP era 31 veces todo lo que se negoció ese día.
La capacidad de la tesis (ejecutabilidad_y_costos_OE1.txt §6.4) supone tomar
como mucho el 10% del monto diario. Lo que se blinda:

  * ninguna ejecución supera participación × monto del día, y un día sin
    negociación no admite orden;
  * lo que no se ejecuta queda PENDIENTE (en soles) y se completa los días
    siguientes; una decisión nueva lo reemplaza;
  * el impacto es Y·σ·√(q/V)·q con σ y V medidos con datos PREVIOS al día;
  * sin `Liquidez` el entorno se comporta exactamente como antes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.env.costs import CostModel, Liquidez  # noqa: E402
from src.env.policies import EqualWeight, run_policy  # noqa: E402
from src.env.portfolio_env import EnvConfig, PortfolioEnv  # noqa: E402
from test_portfolio_env import panel_sintetico  # noqa: E402


def _liquidez(p, monto=50_000.0, participacion=0.10, Y=0.0, sigma=0.02):
    T, n = p.prices.shape
    m = np.full((T, n), float(monto)) if np.isscalar(monto) else np.asarray(monto, float)
    return Liquidez(monto=m, adv=m.copy(), sigma=np.full((T, n), sigma),
                    participacion=participacion, impacto_Y=Y)


def _costos(p, liq=None, min_fee=40.0):
    return CostModel(tickers=p.tickers, half_spread_bps=20.0, commission_rate=0.0043,
                     min_fee=min_fee, liquidez=liq)


def _ejecuciones(env, politica):
    ejecutar, out = env._execute, []

    def espia(target, e, v_pre):
        antes = env.units.copy()
        r = ejecutar(target, e, v_pre)
        out.append((e, (env.units - antes) * env.panel.prices[e]))
        return r

    env._execute = espia
    run_policy(env, politica)
    return out


def test_ninguna_ejecucion_supera_el_tope_del_dia():
    p = panel_sintetico(n_dias=120, n_activos=3)
    monto = np.random.default_rng(1).uniform(20_000, 400_000, size=p.prices.shape)
    monto[::7, 1] = 0.0  # días sin negociación en A1
    liq = _liquidez(p, monto=monto)
    env = PortfolioEnv(p, _costos(p, liq), EnvConfig(action_mode="weights", rebalance_every=1))
    for e, q in _ejecuciones(env, EqualWeight()):
        assert np.all(np.abs(q) <= 0.10 * monto[e] + 1e-6), f"día {e}: {q} supera el 10% de {monto[e]}"


def test_dia_sin_negociacion_no_admite_orden():
    p = panel_sintetico(n_dias=60, n_activos=3)
    monto = np.full(p.prices.shape, 1e9)
    monto[:, 2] = 0.0
    env = PortfolioEnv(p, _costos(p, _liquidez(p, monto=monto)),
                       EnvConfig(action_mode="weights", cartera_inicial="caja"))
    run_policy(env, EqualWeight())
    assert env.units[2] == 0.0, "se compró un activo que nunca se negoció"


def test_la_orden_pendiente_se_completa_en_los_dias_siguientes():
    # 1/N TRIMESTRAL: decide una sola vez y no vuelve a decidir en 63 días.
    # Con S/1.8 MM y un tope de S/20k diarios por activo (10% de S/200k), la
    # compra de ~S/600k por activo toma ~30 días; tiene que completarse sola.
    p = panel_sintetico(n_dias=80, n_activos=3)
    env = PortfolioEnv(p, _costos(p, _liquidez(p, monto=200_000.0)),
                       EnvConfig(action_mode="weights", rebalance_every=63, cartera_inicial="caja"))
    res = run_policy(env, EqualWeight())
    caja = res["weights"][:, -1]
    assert caja[1] > 0.9, "el primer día no puede invertir más que el tope"
    assert caja[40] < 0.05, f"la orden pendiente no se completó: caja {caja[40]:.1%} al día 40"


def test_una_decision_nueva_reemplaza_la_pendiente():
    p = panel_sintetico(n_dias=40, n_activos=2)
    env = PortfolioEnv(p, _costos(p, _liquidez(p, monto=200_000.0)),
                       EnvConfig(action_mode="weights", rebalance_every=1))
    env.step(np.array([1.0, 0.0, 0.0]))      # pide todo en A0: queda pendiente
    assert env.pendiente[0] > 0
    env.step(np.array([0.0, 0.0, 1.0]))      # ahora pide todo en caja
    assert env.pendiente[0] <= 0, "siguió comprando A0 tras una decisión que lo descarta"


def test_las_migajas_bajo_la_banda_no_quedan_pendientes():
    p = panel_sintetico(n_dias=40, n_activos=2)
    env = PortfolioEnv(p, _costos(p, _liquidez(p, monto=200_000.0)), EnvConfig(action_mode="weights"))
    env.step(np.array([1.0, 1.0, 0.0]))
    assert np.all((env.pendiente == 0) | (np.abs(env.pendiente) >= env.band))


def test_impacto_raiz_cuadrada_exacto():
    p = panel_sintetico(n_dias=10, n_activos=2)
    liq = _liquidez(p, monto=1e6, Y=0.65, sigma=0.015)
    cm = CostModel(tickers=p.tickers, half_spread_bps=0.0, commission_rate=0.0, min_fee=0.0,
                   igv=0.0, fees_rate=0.0, liquidez=liq)
    q = np.array([40_000.0, 0.0])
    esperado = 0.65 * 0.015 * np.sqrt(40_000.0 / 1e6) * 40_000.0  # S/78
    assert cm.cost_of_trades(q, 3).tolist() == pytest.approx([esperado, 0.0])


def test_sigma_y_monto_medio_son_causales():
    from src.env.costs import _causal_rodante

    x = np.arange(30, dtype=float).reshape(-1, 1)
    media = _causal_rodante(x, 5, "mean")
    # El valor del día e usa los días e-5..e-1: nunca el propio día.
    assert media[10, 0] == pytest.approx(np.mean(x[5:10, 0]))


def test_sin_liquidez_no_cambia_nada():
    p = panel_sintetico(n_dias=120, n_activos=3)
    a = run_policy(PortfolioEnv(p, _costos(p), EnvConfig(action_mode="weights", rebalance_every=5)),
                   EqualWeight())
    b = run_policy(PortfolioEnv(p, _costos(p), EnvConfig(action_mode="weights", rebalance_every=5)),
                   EqualWeight())
    assert np.array_equal(a["equity"], b["equity"])
    # y con un tope que nunca muerde, el resultado es el mismo que sin tope
    c = run_policy(PortfolioEnv(p, _costos(p, _liquidez(p, monto=1e15)),
                                EnvConfig(action_mode="weights", rebalance_every=5)), EqualWeight())
    assert np.allclose(a["equity"], c["equity"], rtol=1e-12)


def test_liquidez_real_si_existe():
    from src.env.costs import LIQUIDEZ_BLOOMBERG

    if not LIQUIDEZ_BLOOMBERG.exists():
        pytest.skip("sin el volcado de Bloomberg (licencia: no va a git)")
    from src.env import costos_observados, load_panel

    panel = load_panel(view="solo_mercado", warmup=250)
    liq = costos_observados(panel).liquidez
    i0 = panel.first_tradable_index
    assert liq.monto.shape == panel.prices.shape
    assert np.isfinite(liq.adv[i0:]).all() and np.isfinite(liq.sigma[i0:]).all()
    assert (liq.monto >= 0).all()
    # la mayoría de los días operables hubo negociación
    assert (liq.monto[i0:] > 0).mean() > 0.85
