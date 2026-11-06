# -*- coding: utf-8 -*-
"""OE1 — los tres algoritmos de R7 (PPO, SAC, DDPG) sobre el MISMO entorno.

POR QUE UN MODULO Y NO TRES SCRIPTS. El algoritmo se instanciaba a mano en cinco
scripts. Si SAC y DDPG se agregaban igual, cada script terminaria con su propia
version de los hiperparametros y nadie se daria cuenta de que los tres brazos
no se comparan en igualdad de condiciones: es la deriva que este proyecto ya
sufrio tres veces. Aca se fija UNA vez como se construye cada uno.

D3 ENMENDADA (2026-09-26): el documento de tesis compromete PPO, DDPG y SAC
(O3, R7). Se implementan los tres. PPO sigue siendo el primario.

EL ENVOLTORIO DE ACCION DE LOS OFF-POLICY, y por que es valido.
El entorno declara la accion en [-10, 10] y adentro aplica tanh: en modo
"delta" el movimiento de la cartera es  Δ = action_scale · tanh(a).  Eso esta
pensado para la gaussiana SIN COTA de PPO. SAC y DDPG ya ACOTAN su salida con
su propio tanh a u ∈ [-1, 1], y SB3 la reescala a los limites del espacio:
el entorno recibiria a = 10u y calcularia tanh(10u) — DOBLE APLASTAMIENTO, que
satura con |u| > 0.3. Y en la fase de arranque, que sortea acciones uniformes
en [-10, 10], el agente haria casi siempre el movimiento maximo.

`AccionAcotada` expone el espacio [-1, 1] y entrega a = artanh(x). Entonces
tanh(a) = x y  Δ = action_scale · x  EXACTAMENTE:
  * es una BIYECCION: el conjunto de carteras alcanzables es el mismo que el
    de PPO, Δ ∈ (-s, s) por activo. No se recorta ni se agrega nada;
  * x = 0 sigue siendo "no operar" exacto (D2 enmendada);
  * no toca NADA de lo que define el entorno —transicion, costos, mascara,
    recompensa, observacion, reloj t+1—, que dependen solo de Δ. Cambia como
    la red ESCRIBE la decision, no el problema.
La version ingenua —declarar [-1, 1] y pasar x sin transformar— NO es valida:
daria Δ = s·tanh(x), con maximo 0.76·s, y encogeria el conjunto alcanzable.
PPO NO pasa por el envoltorio: sus 134 corridas registradas siguen siendo
comparables con las nuevas.

LA EXPLORACION NO TIENE DEFECTO en SAC ni en DDPG. Con los defectos de SB3, PPO
rotaba 206 veces al año y el peaje se comia todo (D22). La perilla equivalente
—el coeficiente de entropia de SAC, la σ del ruido de DDPG— se CALIBRA POR
ROTACION EN TRAIN, igual que D22, y se pasa explicita. Una constante que nadie
eligio es exactamente la trampa que las guardas de rewards.py evitan.
"""
from __future__ import annotations

from typing import Any

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:  # pragma: no cover - depende del entorno de ejecucion
    gym = None
    spaces = None

ALGORITMOS = ("ppo", "sac", "ddpg")

#: Red de los tres. Chica a proposito (~3,300 dias de UNA trayectoria); ver
#: train_ppo_oe1.py. Tiene que ser la misma para que la comparacion mida el
#: algoritmo y no la capacidad.
NET_ARCH = [64, 64]
GAMMA = 0.99
BATCH = 256

#: Margen para que artanh no devuelva infinito en los bordes. Con 1e-6 el
#: maximo alcanzable es artanh(1-1e-6) ≈ 7.25 —dentro de [-10, 10]— y
#: tanh de eso difiere de 1 en 1e-6: el mismo borde practico que PPO.
_EPS_BORDE = 1e-6


class AccionAcotada(gym.ActionWrapper if gym else object):
    """Reparametriza la accion de un agente off-policy: x ∈ [-1, 1] -> artanh(x).

    Solo vale para `action_mode="delta"`: es la forma adoptada (D2 enmendada) y
    la unica en la que el entorno aplica tanh. En los otros modos la identidad
    tanh(artanh(x)) = x no describe lo que hace el entorno, asi que se rechaza
    en vez de aplicarse en silencio.
    """

    def __init__(self, env):
        modo = env.cfg.action_mode
        if modo != "delta":
            raise ValueError(
                f"AccionAcotada solo aplica a action_mode='delta' (llego {modo!r}): "
                "es el unico modo en que el entorno aplica tanh a la accion"
            )
        super().__init__(env)
        n = env.action_space.shape[0]
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(n,), dtype=np.float32)

    def action(self, accion):
        x = np.clip(np.asarray(accion, dtype=np.float64), -1.0 + _EPS_BORDE, 1.0 - _EPS_BORDE)
        return np.arctanh(x)


def necesita_envoltorio(algo: str) -> bool:
    """Los off-policy acotan su salida con tanh; PPO no."""
    return _valida(algo) != "ppo"


def exploracion(algo: str, *, log_std: float | None = None,
                ent_coef: float | None = None, sigma: float | None = None) -> dict[str, Any]:
    """La perilla de exploracion de cada algoritmo, validada y SIN defecto.

    Devuelve los campos que entran a la configuracion registrada (D10). Para
    PPO son exactamente los de siempre, para que el hash de sus corridas no
    cambie (ver `config_registro`).
    """
    algo = _valida(algo)
    if algo == "ppo":
        if log_std is None:
            raise ValueError("PPO necesita log_std (D22: -2.0, calibrado por rotacion)")
        return {"log_std_init": float(log_std)}
    if algo == "sac":
        if ent_coef is None:
            raise ValueError(
                "SAC necesita ent_coef explicito, calibrado por rotacion en train "
                "(misma regla que D22). El 'auto' de SB3 no esta calibrado."
            )
        return {"ent_coef": float(ent_coef)}
    if sigma is None:
        raise ValueError(
            "DDPG necesita la sigma del ruido de accion, calibrada por rotacion en "
            "train (misma regla que D22)"
        )
    return {"noise_sigma": float(sigma)}


def config_registro(algo: str, explora: dict[str, Any]) -> dict[str, Any]:
    """Campos del algoritmo que van al registro de configuraciones (D10).

    PARA PPO DEVUELVE EXACTAMENTE LO QUE LOS SCRIPTS ANOTABAN ANTES
    ({algoritmo, net_arch, log_std_init}). El contador identifica una
    estrategia por el hash del JSON de su configuracion: una clave nueva en las
    corridas de PPO las haria contar como estrategias distintas de las 134 ya
    registradas y inflaria el Sharpe deflactado sin que nada hubiera cambiado.
    """
    algo = _valida(algo)
    cfg: dict[str, Any] = {"algoritmo": algo.upper(), "net_arch": list(NET_ARCH), **explora}
    if algo != "ppo":
        cfg["envoltorio_accion"] = "artanh"
    return cfg


def envuelve(env, algo: str):
    """Aplica el envoltorio si el algoritmo lo necesita. Idempotente para PPO."""
    return AccionAcotada(env) if necesita_envoltorio(algo) else env


def construye_modelo(algo: str, entorno, *, semilla: int, explora: dict[str, Any],
                     timesteps: int, ent_coef_ppo: float = 0.0):
    """Instancia el algoritmo con los hiperparametros fijados para OE1.

    `entorno` ya tiene que venir envuelto (ver `envuelve`) para los off-policy.
    `ent_coef_ppo` existe solo porque train_ppo_oe1.py lo exponia; D22 lo fija
    en 0. (El registro nunca lo anoto, asi que no hay como auditar si alguna
    corrida vieja uso otro valor.)
    Se verifica: si el espacio de accion no es [-1, 1], el modelo aprenderia
    con doble tanh y nadie se daria cuenta.
    """
    algo = _valida(algo)
    if algo == "ppo":
        from stable_baselines3 import PPO

        # IDENTICO a la instanciacion de ablacion_r8.py / train_ppo_oe1.py hasta
        # el 2026-09-26. No cambiar sin revalidar la comparabilidad.
        return PPO(
            "MlpPolicy",
            entorno,
            seed=semilla,
            verbose=0,
            n_steps=512,
            batch_size=BATCH,
            gamma=GAMMA,
            ent_coef=ent_coef_ppo,
            policy_kwargs={"net_arch": list(NET_ARCH), "log_std_init": explora["log_std_init"]},
        )

    espacio = entorno.action_space
    if not (np.allclose(espacio.low, -1.0) and np.allclose(espacio.high, 1.0)):
        raise ValueError(
            f"{algo.upper()} necesita el entorno envuelto con AccionAcotada "
            f"(espacio [-1, 1]); llego [{espacio.low.min()}, {espacio.high.max()}]"
        )
    # El buffer guarda la trayectoria entera: con <=1M pasos entra en memoria y
    # no se descarta experiencia de train (que es poca: ~1,500-2,500 dias).
    comunes = dict(
        seed=semilla,
        verbose=0,
        batch_size=BATCH,
        gamma=GAMMA,
        buffer_size=int(min(max(timesteps, 10_000), 1_000_000)),
        policy_kwargs={"net_arch": list(NET_ARCH)},
    )
    if algo == "sac":
        from stable_baselines3 import SAC

        return SAC("MlpPolicy", entorno, ent_coef=explora["ent_coef"], **comunes)

    from stable_baselines3 import DDPG
    from stable_baselines3.common.noise import NormalActionNoise

    n = espacio.shape[0]
    ruido = NormalActionNoise(mean=np.zeros(n), sigma=explora["noise_sigma"] * np.ones(n))
    return DDPG("MlpPolicy", entorno, action_noise=ruido, **comunes)


def _valida(algo: str) -> str:
    a = algo.lower()
    if a not in ALGORITMOS:
        raise ValueError(f"algoritmo desconocido: {algo!r}; validos: {ALGORITMOS}")
    return a
