# -*- coding: utf-8 -*-
"""Guarda del retomado de scripts/ablacion_r8.py (2026-10-29).

La ablación R8 con DDPG se cortó dos veces y se perdió trabajo porque el script
no sabía retomar. El retomado salta las (vista, pliegue, semilla) ya hechas;
lo que hay que blindar es que NO retome cuando no debe: con otra configuración
o con otro panel mezclaría dos experimentos en una sola tabla sin avisar.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ablacion_r8 import compatibilidad, guarda, hechas  # noqa: E402
from src.env.portfolio_env import VERSION_SIMULADOR  # noqa: E402

CONFIG = {
    "views": ["solo_mercado"], "timesteps": 150_000, "seeds": 3, "folds": 3,
    "reward": "dsr", "lam": None, "kappa": None, "algo": "ddpg", "log_std": -2.0,
    "sac_ent_coef": None, "ddpg_sigma": 0.16, "action_mode": "delta",
    "action_scale": 0.05, "rebalance_every": 1, "n_envs": None,
    "out": "a.json", "retoma": None, "registro": "r.jsonl",
}
SHA = "a" * 64


def _previo(**cambios) -> dict:
    return {"config": {**CONFIG, **cambios}, "panel_sha256": SHA,
            "simulador": VERSION_SIMULADOR, "vistas": {}}


def test_misma_configuracion_retoma_sin_avisos():
    assert compatibilidad(_previo(), CONFIG, SHA) == []


def test_vistas_semillas_y_rutas_se_pueden_cambiar_al_retomar():
    previo = _previo(views=["completa"], seeds=10, out="otro.json", retoma="x")
    assert compatibilidad(previo, CONFIG, SHA) == []


@pytest.mark.parametrize("clave, valor", [
    ("timesteps", 50_000), ("ddpg_sigma", 0.3), ("reward", "logret"),
    ("algo", "sac"), ("action_scale", 0.1), ("folds", 5),
])
def test_otra_configuracion_no_retoma(clave, valor):
    with pytest.raises(ValueError, match=clave):
        compatibilidad(_previo(**{clave: valor}), CONFIG, SHA)


def test_otro_panel_no_retoma():
    with pytest.raises(ValueError, match="panel"):
        compatibilidad(_previo(), CONFIG, "b" * 64)


def test_la_exploracion_de_otro_algoritmo_no_importa():
    # Un DDPG no deja de ser el mismo experimento porque cambie el log_std de PPO.
    assert compatibilidad(_previo(log_std=-1.0), CONFIG, SHA) == []


PARCIAL_11OCT = {"config": {"views": ["solo_mercado"], "algo": "ddpg", "ddpg_sigma": 0.16,
                             "folds": 3, "seeds": 3, "timesteps": 150_000, "reward": "dsr",
                             "action_mode": "delta", "action_scale": 0.05}}


def test_otro_simulador_no_retoma():
    with pytest.raises(ValueError, match="simulador"):
        compatibilidad({**_previo(), "simulador": "1999-01-01"}, CONFIG, SHA)


def test_parcial_anterior_a_la_correccion_del_simulador_no_retoma():
    # Forma real de ablacion_r8_ddpg_{vista}.parcial.json (11-oct): no trae
    # versión de simulador porque es anterior a la corrección de costos.
    with pytest.raises(ValueError, match="anterior a 2026-10-29"):
        compatibilidad(PARCIAL_11OCT, CONFIG, SHA)


def test_artefacto_sin_huella_de_panel_retoma_con_avisos():
    # Sin huella de panel y con menos claves: se acepta, diciendo qué no se
    # pudo verificar.
    parcial = {**PARCIAL_11OCT, "simulador": VERSION_SIMULADOR}
    avisos = compatibilidad(parcial, CONFIG, SHA)
    assert any("panel" in a for a in avisos)
    assert any("rebalance_every" in a for a in avisos)
    assert not any("log_std" in a for a in avisos)


def test_hechas_indexa_por_semilla():
    res = {"vistas": {"v": {"pliegue1": [{"seed": 2, "x": 1}, {"seed": 0, "x": 2}]}}}
    assert set(hechas(res, "v", 1)) == {0, 2}
    assert hechas(res, "v", 0) == {}
    assert hechas(res, "otra", 1) == {}


def test_guarda_reemplaza_sin_dejar_temporal(tmp_path):
    salida = tmp_path / "sub" / "a.json"
    guarda({"n": 1}, salida)
    guarda({"n": 2}, salida)
    assert json.loads(salida.read_text(encoding="utf-8")) == {"n": 2}
    assert not list(salida.parent.glob("*.tmp"))
