# -*- coding: utf-8 -*-
"""Humo del entorno de OE1 sobre el panel real: baselines, costos y frecuencia.

No entrena nada. Corre las políticas de referencia dentro del entorno para
verificar que la economía del simulador tiene sentido ANTES de meter un agente,
y de paso contesta con datos la P1 del especialista (¿a qué frecuencia tiene
sentido rebalancear?).

    python scripts/smoke_env_oe1.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.env import (  # noqa: E402
    CashOnly,
    EnvConfig,
    EqualWeight,
    PortfolioEnv,
    RandomDirichlet,
    load_panel,
    run_policy,
    snapshot_cost_model,
    zero_cost_model,
)

import numpy as np  # noqa: E402


def main() -> None:
    panel = load_panel(view="solo_mercado", warmup=250)
    costos = snapshot_cost_model(panel.tickers)
    sin_costo = zero_cost_model(panel.tickers)

    print(
        f"panel: {panel.n_steps} fechas x {panel.n_assets} activos | "
        f"primer día con los 7 listados: {str(panel.dates[panel.first_tradable_index])[:10]}"
    )
    print("\ncosto de ida y vuelta por activo (pbs, órdenes de S/250k):")
    for t, b in zip(panel.tickers, costos.roundtrip_bps(notional=250_000)):
        print(f"   {t:9s} {b:7.1f}")
    print(f"   banda derivada del mínimo por orden: S/{costos.band_notional():,.0f}")

    escenarios = [
        ("1/N diario  sin costo", sin_costo, 1, EqualWeight()),
        ("1/N diario  con costo", costos, 1, EqualWeight()),
        ("1/N semanal con costo", costos, 5, EqualWeight()),
        ("1/N mensual con costo", costos, 21, EqualWeight()),
        ("1/N trimestral", costos, 63, EqualWeight()),
        ("comprar y mantener", costos, 10**9, EqualWeight()),
        ("solo caja", costos, 1, CashOnly()),
    ]

    print(
        f"\n{'estrategia':22s} {'ret.total':>10s} {'sharpe':>7s} {'maxDD':>7s} "
        f"{'rot/año':>8s} {'costo S/':>11s}"
    )
    for etiqueta, cm, freq, pol in escenarios:
        env = PortfolioEnv(panel, cm, EnvConfig(action_mode="weights", rebalance_every=freq))
        s = run_policy(env, pol)["summary"]
        print(
            f"{etiqueta:22s} {s['retorno_total']:9.1%} {s['sharpe']:7.2f} "
            f"{s['max_drawdown']:7.1%} {s['rotacion_anual']:8.2f} {s['costo_total']:11,.0f}"
        )

    # Banda nula de D10, en versión reducida: la distribución de lo que consigue
    # el azar en este universo, con las mismas restricciones y los mismos costos.
    # La asignación se sortea UNA vez y se mantiene; la frecuencia de rebalanceo
    # la fija el entorno (ver la nota en RandomDirichlet sobre por qué).
    print()
    for freq, etiqueta in [(21, "rebalanceo mensual"), (10**9, "sin rebalanceo")]:
        finales = []
        for semilla in range(60):
            env = PortfolioEnv(
                panel, costos, EnvConfig(action_mode="weights", rebalance_every=freq)
            )
            finales.append(run_policy(env, RandomDirichlet(seed=semilla))["summary"]["retorno_total"])
        q = np.percentile(finales, [5, 50, 95])
        print(
            f"banda nula, 60 carteras aleatorias ({etiqueta}): "
            f"p5 {q[0]:6.1%} | mediana {q[1]:6.1%} | p95 {q[2]:6.1%}"
        )


if __name__ == "__main__":
    main()
