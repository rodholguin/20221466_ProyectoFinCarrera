"""OE1 — entorno de RL y baselines para el agente de portafolio sobre la BVL.

Mapa del paquete:
    panel.py         carga el panel de R6 y lo vuelve arrays (sin pandas adentro)
    features.py      vistas de señales (R8) y normalización causal (D6)
    costs.py         modelo de costos por activo (D7), listo para spread temporal
    rewards.py       DSR primaria, DDR y log-retorno neto (D4)
    portfolio_env.py el entorno: reloj, contabilidad, máscara y caja (D2/D8/D9/D13)
    policies.py      baselines corriendo DENTRO del mismo simulador (D10)

Las decisiones y su porqué viven en `docs/decisiones_pendientes_OE1.txt`.
"""
from .costs import CostModel, snapshot_cost_model, zero_cost_model
from .features import VIEWS, build_features
from .panel import PanelData, load_panel
from .policies import (
    CashOnly,
    EqualWeight,
    FixedWeights,
    Markowitz,
    RandomDirichlet,
    ledoit_wolf_cov,
    run_policy,
)
from .portfolio_env import EnvConfig, PortfolioEnv
from .rewards import DifferentialDownside, DifferentialSharpe, NetLogReturn, make_reward

__all__ = [
    "CostModel",
    "snapshot_cost_model",
    "zero_cost_model",
    "VIEWS",
    "build_features",
    "PanelData",
    "load_panel",
    "EnvConfig",
    "PortfolioEnv",
    "EqualWeight",
    "CashOnly",
    "FixedWeights",
    "Markowitz",
    "ledoit_wolf_cov",
    "RandomDirichlet",
    "run_policy",
    "DifferentialSharpe",
    "DifferentialDownside",
    "NetLogReturn",
    "make_reward",
]
