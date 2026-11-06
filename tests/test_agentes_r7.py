"""Tests de los algoritmos de R7 (PPO, SAC, DDPG) y del envoltorio de acción.

QUÉ SE PRUEBA, y el orden es por importancia:

    1. EL ENVOLTORIO ES UNA BIYECCIÓN SOBRE EL MISMO ENTORNO. Para cualquier
       x ∈ [-1, 1], el entorno envuelto produce EXACTAMENTE los mismos pesos,
       costos y patrimonio que el entorno crudo con a = artanh(x). Es la
       propiedad que hace defendible comparar SAC y DDPG contra PPO: si falla,
       los off-policy estarían resolviendo otro problema.
    2. x = 0 SIGUE SIENDO "NO OPERAR" (D2 enmendada), y el borde alcanzable es
       el mismo que el de PPO (el conjunto de carteras no se encoge).
    3. PPO NO CAMBIA DE HASH EN EL REGISTRO. Si la configuración que anota
       ablacion_r8.py para PPO cambiara aunque sea en una clave, las mismas
       estrategias contarían como nuevas en el Sharpe deflactado de D10.
    4. LAS GUARDAS FALLAN TEMPRANO: sin perilla de exploración explícita, sin
       envoltorio, o con un modo de acción donde el envoltorio no aplica.
    5. Los tres algoritmos se construyen y aprenden unos pasos sobre un panel
       sintético (plomería, no desempeño).

Corre con pytest o directo:  python tests/test_agentes_r7.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_portfolio_env import panel_sintetico  # noqa: E402

from src.agents import (  # noqa: E402
    AccionAcotada,
    config_registro,
    construye_modelo,
    envuelve,
    exploracion,
)
from src.env.costs import CostModel  # noqa: E402
from src.env.portfolio_env import EnvConfig, PortfolioEnv  # noqa: E402
from src.env.registro import REGISTRO, hash_config  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


def _env_delta(panel, escala: float = 0.05) -> PortfolioEnv:
    """Con costos reales: la biyección tiene que sostenerse también en el peaje."""
    costos = CostModel(tickers=panel.tickers, half_spread_bps=110.0,
                       commission_rate=0.0043, min_fee=40.0)
    return PortfolioEnv(panel, costos, EnvConfig(action_mode="delta", rebalance_every=1,
                                                 band_notional=0.0, action_scale=escala))


def _corre(env, acciones) -> dict:
    env.reset()
    for a in acciones:
        res = env.step(a)
        if (res[2] or res[3]) if len(res) == 5 else res[2]:
            break
    base = env.unwrapped if hasattr(env, "unwrapped") else env
    return {
        "pesos": np.asarray(base.history["weights"]),
        "costo": np.asarray(base.history["cost"]),
        "patrimonio": np.asarray(base.equity_curve),
    }


# --------------------------------------------------------------------------
# 1. biyección
# --------------------------------------------------------------------------
def test_envoltorio_equivale_al_entorno_crudo_con_artanh():
    p = panel_sintetico(n_dias=60, n_activos=3)
    rng = np.random.default_rng(11)
    n = 4  # 3 activos + caja
    xs = rng.uniform(-0.999, 0.999, size=(59, n))

    envuelto = _corre(AccionAcotada(_env_delta(p)), xs)
    crudo = _corre(_env_delta(p), np.arctanh(xs))

    for k in ("pesos", "costo", "patrimonio"):
        assert np.allclose(envuelto[k], crudo[k], rtol=0, atol=1e-12), f"difiere en {k}"


def test_envoltorio_entrega_el_delta_exacto():
    """tanh(artanh(x)) = x: el movimiento pedido es action_scale · x."""
    p = panel_sintetico()
    env = AccionAcotada(_env_delta(p))
    xs = np.linspace(-0.99, 0.99, 9)
    assert np.allclose(np.tanh(env.action(xs)), xs, atol=1e-12)


# --------------------------------------------------------------------------
# 2. no operar y borde alcanzable
# --------------------------------------------------------------------------
def test_accion_cero_envuelta_no_opera_nunca():
    p = panel_sintetico()
    env = AccionAcotada(_env_delta(p))
    r = _corre(env, [np.zeros(4)] * 200)
    assert np.allclose(env.unwrapped.history["turnover"], 0.0), "x=0 produjo operaciones"
    assert r["costo"].sum() == 0.0, "x=0 pagó costo"


def test_borde_alcanzable_es_el_de_ppo():
    """El conjunto de carteras no se encoge: el borde envuelto ≈ tanh(10) de PPO."""
    env = AccionAcotada(_env_delta(panel_sintetico()))
    borde_envuelto = np.tanh(env.action(np.array([1.0])))[0]
    borde_ppo = np.tanh(10.0)
    assert borde_envuelto > 1 - 2e-6
    assert abs(borde_envuelto - borde_ppo) < 2e-6
    assert np.all(np.abs(env.action(np.array([-1.0, 1.0]))) < 10.0), "sale del espacio del entorno"


# --------------------------------------------------------------------------
# 3. el hash de PPO en el registro no cambia
# --------------------------------------------------------------------------
def test_config_de_ppo_no_cambia_el_hash_del_registro():
    ruta = RAIZ / REGISTRO
    if not ruta.exists():
        return  # sin registro no hay contra qué comparar
    filas = [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines() if x.strip()]
    ppo = [f for f in filas if f["config"].get("algoritmo") == "PPO"
           and "log_std_init" in f["config"]]
    assert ppo, "el registro no tiene corridas PPO con log_std_init"
    for fila in ppo[-20:]:
        viejo = fila["config"]
        nuevo = {k: v for k, v in viejo.items()
                 if k not in ("algoritmo", "net_arch", "log_std_init")}
        nuevo.update(config_registro("ppo", exploracion("ppo", log_std=viejo["log_std_init"])))
        assert hash_config(nuevo) == hash_config(viejo), (
            f"la configuración PPO cambió de hash: {viejo} -> {nuevo}"
        )


def test_conteo_no_separa_por_claves_vacias(tmp_path):
    """`reward_kwargs: {}` y la clave ausente son la MISMA estrategia (D10)."""
    from src.env.registro import conteo, registra
    ruta = tmp_path / "registro.jsonl"
    base = {"view": "solo_mercado", "reward": "dsr", "fold": 0, "seed": 0}
    registra(base, "val", ruta=ruta)
    registra(base | {"reward_kwargs": {}, "seed": 1}, "val", ruta=ruta)
    registra(base | {"reward_kwargs": None, "seed": 2}, "val", ruta=ruta)
    assert conteo(ruta)["configuraciones_distintas"] == 1
    registra(base | {"reward_kwargs": {"lam": 0.65}}, "val", ruta=ruta)  # esta SÍ es otra
    assert conteo(ruta)["configuraciones_distintas"] == 2


def test_off_policy_se_distinguen_en_el_registro():
    sac = config_registro("sac", exploracion("sac", ent_coef=0.01))
    ddpg = config_registro("ddpg", exploracion("ddpg", sigma=0.1))
    assert sac["algoritmo"] == "SAC" and ddpg["algoritmo"] == "DDPG"
    assert sac["envoltorio_accion"] == ddpg["envoltorio_accion"] == "artanh"
    assert "log_std_init" not in sac and "log_std_init" not in ddpg


# --------------------------------------------------------------------------
# 4. guardas
# --------------------------------------------------------------------------
def _falla(fn, *a, **kw) -> bool:
    try:
        fn(*a, **kw)
    except ValueError:
        return True
    return False


def test_exploracion_sin_defecto():
    assert _falla(exploracion, "ppo")
    assert _falla(exploracion, "sac")
    assert _falla(exploracion, "ddpg")
    assert _falla(exploracion, "td3", sigma=0.1)


def test_envoltorio_rechaza_modos_sin_tanh():
    p = panel_sintetico()
    for modo in ("weights", "logits"):
        env = PortfolioEnv(p, CostModel(tickers=p.tickers), EnvConfig(action_mode=modo))
        assert _falla(AccionAcotada, env), f"aceptó action_mode={modo}"


def test_off_policy_rechaza_entorno_sin_envolver():
    env = _env_delta(panel_sintetico())
    assert _falla(construye_modelo, "sac", env, semilla=0,
                  explora={"ent_coef": 0.01}, timesteps=1000)


def test_ppo_no_se_envuelve():
    env = _env_delta(panel_sintetico())
    assert envuelve(env, "ppo") is env
    assert isinstance(envuelve(env, "sac"), AccionAcotada)


# --------------------------------------------------------------------------
# 5. plomería: los tres construyen, aprenden y predicen dentro del espacio
# --------------------------------------------------------------------------
def test_los_tres_algoritmos_aprenden_unos_pasos():
    try:
        import stable_baselines3  # noqa: F401
    except ImportError:
        return
    p = panel_sintetico(n_dias=120)
    perillas = {"ppo": {"log_std": -2.0}, "sac": {"ent_coef": 0.01}, "ddpg": {"sigma": 0.1}}
    for algo, kw in perillas.items():
        env = envuelve(_env_delta(p), algo)
        modelo = construye_modelo(algo, env, semilla=0, explora=exploracion(algo, **kw),
                                  timesteps=600)
        modelo.learn(total_timesteps=600, progress_bar=False)
        obs, _ = env.reset()
        accion, _ = modelo.predict(obs, deterministic=True)
        assert accion.shape == (4,)
        assert np.all(np.isfinite(accion))
        if algo != "ppo":
            assert np.all(np.abs(accion) <= 1.0 + 1e-6), f"{algo} salió de [-1, 1]"


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {nombre}")
