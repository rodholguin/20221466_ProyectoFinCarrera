"""OE1 — funciones de recompensa (D4).

Los tres brazos decididos el 2026-09-03, y no más: cada brazo adicional
multiplica las corridas y degrada el Sharpe deflactado (D10).

    PRIMARIA  DifferentialSharpe   (DSR, Moody-Saffell 1998/2001)
    V1        DifferentialDownside (DDR, semivarianza) — era la primaria
    V0        NetLogReturn         — control, sin ajuste por riesgo

POR QUÉ LA FORMA DIFERENCIAL Y NO "EL SHARPE AL FINAL DEL EPISODIO":
el Sharpe se define sobre un periodo T, pero el RL necesita señal POR PASO. El
DSR es la derivada del Sharpe respecto al peso del último dato, calculada con
estimadores exponenciales; sumar los incrementos aproxima el Sharpe del periodo.

EL PUNTO QUE NO ES COSMÉTICO — MARKOV. Cualquier término que dependa de la
historia (varianza, Sharpe, drawdown) rompe la propiedad de Markov: la
recompensa deja de ser función solo del estado y la acción actuales, y el agente
optimiza una señal que no puede explicar con lo que observa. Por eso cada
recompensa expone `state()`, y el entorno LO CONCATENA AL VECTOR DE OBSERVACIÓN.
Sin eso, el problema está mal planteado.

GANANCIA DEL CAMBIO A DSR: elimina λ. El ajuste por riesgo está dentro de la
forma funcional, no como un término ponderado que hay que calibrar. Se cambia λ
por η (tasa de adaptación), que es una vida media interpretable y se
pre-registra por razonamiento económico en vez de ajustarse contra resultados.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

# Piso del denominador. Los primeros pasos tienen varianza ~0 y la razón
# explota; por debajo de esto la recompensa es 0 y solo se acumulan
# estadísticos. Con eta=1/60 el calentamiento dura unas pocas decenas de pasos.
_EPS = 1e-8


class Reward(ABC):
    """Recompensa por paso, con estado suficiente expuesto para la observación."""

    #: nombre corto para el registro de configuraciones (contador de D10)
    name: str = "base"

    @abstractmethod
    def reset(self) -> None:
        """Reinicia los estadísticos. Se llama en cada `env.reset()`."""

    @abstractmethod
    def step(self, net_return: float) -> float:
        """Consume el retorno simple NETO DE COSTOS del periodo y devuelve r_t."""

    @abstractmethod
    def state(self) -> np.ndarray:
        """Estadísticos suficientes que deben ir en la observación."""

    @property
    def state_dim(self) -> int:
        return int(self.state().shape[0])


class NetLogReturn(Reward):
    """V0 — log-retorno neto puro. Control del experimento.

    Sin él no se puede afirmar que el ajuste por riesgo aportó algo. No tiene
    estado: es markoviana por construcción.
    """

    name = "logret"

    def reset(self) -> None:  # noqa: D102
        return None

    def step(self, net_return: float) -> float:  # noqa: D102
        return float(np.log1p(max(net_return, -0.999999)))

    def state(self) -> np.ndarray:  # noqa: D102
        return np.zeros(0, dtype=np.float32)


class DifferentialSharpe(Reward):
    """PRIMARIA — Sharpe diferencial de Moody-Saffell.

        A_t = A_{t-1} + eta·(R_t − A_{t-1})
        B_t = B_{t-1} + eta·(R_t² − B_{t-1})
        r_t = [ B_{t-1}·(R_t − A_{t-1}) − ½·A_{t-1}·(R_t² − B_{t-1}) ]
              / (B_{t-1} − A_{t-1}²)^(3/2)

    Args:
        eta: tasa de adaptación. 1/60 ≈ memoria trimestral en días bursátiles.
            SE PRE-REGISTRA, no se ajusta contra resultados.
        scale: factor multiplicativo sobre la recompensa. No cambia el óptimo;
            solo evita que el gradiente trabaje con números diminutos.
    """

    name = "dsr"

    def __init__(self, eta: float = 1.0 / 60.0, scale: float = 1.0) -> None:
        if not 0.0 < eta <= 1.0:
            raise ValueError("eta debe estar en (0, 1]")
        self.eta = float(eta)
        self.scale = float(scale)
        self.reset()

    def reset(self) -> None:  # noqa: D102
        self.a = 0.0  # media exponencial
        self.b = 0.0  # segundo momento exponencial
        self.n = 0

    def step(self, net_return: float) -> float:  # noqa: D102
        r = float(net_return)
        var = self.b - self.a * self.a
        if var > _EPS:
            num = self.b * (r - self.a) - 0.5 * self.a * (r * r - self.b)
            reward = num / (var ** 1.5)
        else:
            reward = 0.0  # calentamiento: aún no hay dispersión estimable
        self.a += self.eta * (r - self.a)
        self.b += self.eta * (r * r - self.b)
        self.n += 1
        return float(np.clip(reward * self.scale, -1e6, 1e6))

    def state(self) -> np.ndarray:  # noqa: D102
        # Se escalan para que entren al vector de observación en un rango
        # comparable al resto de features ya normalizadas.
        vol = np.sqrt(max(self.b - self.a * self.a, 0.0))
        return np.array([self.a * 100.0, vol * 100.0], dtype=np.float32)


class DifferentialDownside(Reward):
    """V1 — razón de downside diferencial (DDR). Semivarianza en vez de varianza.

    Misma mecánica que el DSR pero el denominador solo acumula las desviaciones
    NEGATIVAS. Es el análogo incremental del Sortino, y era la recompensa
    primaria de la propuesta del 2026-09-02 (ver D4).

        A_t  = A_{t-1}  + eta·(R_t − A_{t-1})
        DD²_t = DD²_{t-1} + eta·(min(R_t, 0)² − DD²_{t-1})

        r_t = (R_t − A_{t-1}/2) / DD_{t-1}                              si R_t > 0
        r_t = [DD²_{t-1}·(R_t − A_{t-1}/2) − ½·A_{t-1}·R_t²] / DD³_{t-1} si R_t ≤ 0
    """

    name = "ddr"

    def __init__(self, eta: float = 1.0 / 60.0, scale: float = 1.0) -> None:
        if not 0.0 < eta <= 1.0:
            raise ValueError("eta debe estar en (0, 1]")
        self.eta = float(eta)
        self.scale = float(scale)
        self.reset()

    def reset(self) -> None:  # noqa: D102
        self.a = 0.0
        self.dd2 = 0.0  # semivarianza exponencial
        self.n = 0

    def step(self, net_return: float) -> float:  # noqa: D102
        r = float(net_return)
        dd = np.sqrt(self.dd2)
        if dd > _EPS:
            if r > 0.0:
                reward = (r - 0.5 * self.a) / dd
            else:
                reward = (self.dd2 * (r - 0.5 * self.a) - 0.5 * self.a * r * r) / (dd ** 3)
        else:
            reward = 0.0
        self.a += self.eta * (r - self.a)
        neg = min(r, 0.0)
        self.dd2 += self.eta * (neg * neg - self.dd2)
        self.n += 1
        return float(np.clip(reward * self.scale, -1e6, 1e6))

    def state(self) -> np.ndarray:  # noqa: D102
        return np.array([self.a * 100.0, np.sqrt(self.dd2) * 100.0], dtype=np.float32)


REWARDS: dict[str, type[Reward]] = {
    "dsr": DifferentialSharpe,
    "ddr": DifferentialDownside,
    "logret": NetLogReturn,
}


def make_reward(name: str, **kwargs) -> Reward:
    """Fábrica por nombre, para que el brazo del experimento sea un string."""
    if name not in REWARDS:
        raise KeyError(f"recompensa desconocida: {name!r}. Opciones: {sorted(REWARDS)}")
    return REWARDS[name](**kwargs)
