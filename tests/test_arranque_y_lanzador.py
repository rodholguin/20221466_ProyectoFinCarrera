# -*- coding: utf-8 -*-
"""D24 (arranque del episodio) y el lanzador paralelo de R8 (2026-11-05)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.env.costs import CostModel  # noqa: E402
from src.env.portfolio_env import EnvConfig, PortfolioEnv  # noqa: E402
from test_portfolio_env import panel_sintetico  # noqa: E402


def _env(p, **cfg):
    return PortfolioEnv(p, CostModel(tickers=p.tickers, half_spread_bps=50.0), EnvConfig(**cfg))


# ------------------------------------------------------------------ D24
def test_evaluacion_arranca_invertida_en_1n_sin_costo():
    p = panel_sintetico(n_activos=4)
    env = _env(p)  # el defecto es el protocolo de evaluación
    w = env._weights(env.t)
    assert np.allclose(w[:4], 0.25) and abs(w[4]) < 1e-12
    assert env._value(env.t) == pytest.approx(env.cfg.initial_capital), "se cobró la entrada"


def test_entrenamiento_arranca_en_cartera_aleatoria_reproducible():
    p = panel_sintetico(n_activos=4)
    env = _env(p, cartera_inicial="aleatoria")
    env.reset(seed=7)
    a = env._weights(env.t).copy()
    env.reset(seed=7)
    assert np.allclose(env._weights(env.t), a), "misma semilla, otra cartera"
    env.reset(seed=8)
    assert not np.allclose(env._weights(env.t), a)
    assert a.sum() == pytest.approx(1.0) and (a >= 0).all()
    assert env._value(env.t) == pytest.approx(env.cfg.initial_capital)


def test_caja_queda_como_sensibilidad():
    p = panel_sintetico(n_activos=3)
    env = _env(p, cartera_inicial="caja")
    assert env._weights(env.t)[-1] == pytest.approx(1.0)


# ------------------------------------------------------------------ lanzador
from lanza_r8 import combina, traslada_registro  # noqa: E402


def _trabajo(vista, pliegue, semilla, ret, sim="v1", sha="x"):
    return {"config": {"algo": "ddpg", "views": [vista], "out": "a"}, "simulador": sim,
            "panel_sha256": sha, "dims": {vista: {"dim_observacion": 99}},
            "baselines": {f"pliegue{pliegue}": {"1/N": {"retorno_total": 0.1}}},
            "vistas": {vista: {f"pliegue{pliegue}": [{"seed": semilla, "retorno_total": ret}]}}}


def test_combina_junta_por_vista_pliegue_y_semilla():
    r = combina([_trabajo("a", 0, 1, 0.2), _trabajo("a", 0, 0, 0.1), _trabajo("b", 1, 0, -0.1)])
    assert [x["seed"] for x in r["vistas"]["a"]["pliegue0"]] == [0, 1]
    assert r["vistas"]["b"]["pliegue1"][0]["retorno_total"] == -0.1
    assert r["config"]["views"] == ["a", "b"] and "out" not in r["config"]


def test_combina_rechaza_mezclar_simuladores_o_paneles():
    with pytest.raises(ValueError, match="simulador"):
        combina([_trabajo("a", 0, 0, 0.1, sim="v1"), _trabajo("a", 0, 1, 0.1, sim="v2")])
    with pytest.raises(ValueError, match="panel"):
        combina([_trabajo("a", 0, 0, 0.1, sha="x"), _trabajo("a", 0, 1, 0.1, sha="y")])


def test_traslada_registro_es_append_y_vacia_el_del_hijo(tmp_path):
    real = tmp_path / "registro.jsonl"
    real.write_text('{"hash": "previo"}\n', encoding="utf-8")
    hijo = tmp_path / "hijo.jsonl"
    hijo.write_text('{"hash": "a"}\n{"hash": "b"}\n', encoding="utf-8")
    assert traslada_registro({"registro": hijo}, real) == 2
    assert [json.loads(x)["hash"] for x in real.read_text(encoding="utf-8").splitlines()] == ["previo", "a", "b"]
    assert not hijo.exists()
    assert traslada_registro({"registro": hijo}, real) == 0  # no duplica
