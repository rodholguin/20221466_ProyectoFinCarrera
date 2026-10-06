"""OE1 — funciones de recompensa (D4).

Los tres brazos decididos el 2026-09-03, y no más: cada brazo adicional
multiplica las corridas y degrada el Sharpe deflactado (D10).

    PRIMARIA  DifferentialSharpe   (DSR, Moody-Saffell 1998/2001)
    V1        DifferentialDownside (DDR, semivarianza) — era la primaria
    V0        NetLogReturn         — control, sin ajuste por riesgo

POR QUÉ LA FORMA DIFERENCIAL Y NO "EL SHARPE AL FINAL DEL EPISODIO":
el Sharpe se define sobre un periodo T, pero el RL necesita señal POR PASO. El
DSR es la derivada del Sharpe EWMA respecto al peso del último dato.

CORREGIDO EL 2026-09-19 — ACÁ DECÍA "sumar los incrementos aproxima el Sharpe
del periodo", Y ESO ES FALSO. Medido en §7.11 de docs/resultados_entorno_OE1.txt
(`scripts/d4_diagnostico_recompensas.py`): la razón entre la suma acumulada y el
Sharpe EWMA terminal va de −14 a −443 en el tramo de entrenamiento y de +187 a
+292 en validación, cuando si telescopara tendría que ser ~1/eta = 60 en los
cuatro casos. La suma es una INTEGRAL DE CAMINO: depende del ORDEN en que llegan
los retornos, no solo de su media y su dispersión. Sobre el tramo 2013-2018
ordena Markowitz (Sharpe del periodo −0.21) POR ENCIMA del 1/N (+0.17), y por un
factor de 5.7. La forma diferencial sigue siendo la correcta para dar señal por
paso; lo que no se puede seguir afirmando es que su suma sea el Sharpe del
periodo.

EL PUNTO QUE NO ES COSMÉTICO — MARKOV. Cualquier término que dependa de la
historia (varianza, Sharpe, drawdown) rompe la propiedad de Markov: la
recompensa deja de ser función solo del estado y la acción actuales, y el agente
optimiza una señal que no puede explicar con lo que observa. Por eso cada
recompensa expone `state()`, y el entorno LO CONCATENA AL VECTOR DE OBSERVACIÓN.
Sin eso, el problema está mal planteado.

GANANCIA DEL CAMBIO A DSR: elimina λ. El ajuste por riesgo está dentro de la
forma funcional, no como un término ponderado que hay que calibrar.
  >> PERO ESE AJUSTE PESA POCO, Y ESTÁ MEDIDO (§7.11). Reordenando,
     r_t ∝ (R−A) − (A/2B)·(R²−B): el castigo a la varianza vale A/(2B), o sea
     es PROPORCIONAL a la media móvil del retorno. En la BVL 2013-2018 ese
     término explica 7-10% de la señal y en 44% de los días sale NEGATIVO —con
     A<0 el DSR PAGA por dispersión en vez de castigarla. No es un defecto de
     implementación: es la forma publicada, usada en un mercado sin deriva.
Se cambia λ por η (tasa de adaptación), que es una vida media interpretable y se
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
    def step(self, net_return: float, turnover: float = 0.0) -> float:
        """Consume el retorno simple NETO DE COSTOS del periodo y devuelve r_t.

        `turnover` es la fracción del portafolio que cambió de manos en el paso.
        Las recompensas de D4 lo IGNORAN —el costo ya está dentro de net_return,
        que es lo que sostiene D7— y solo lo usa el brazo que REABRE esa
        decisión. Va con defecto para no romper a quien no lo pase.
        """

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

    def step(self, net_return: float, turnover: float = 0.0) -> float:  # noqa: D102
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

    def step(self, net_return: float, turnover: float = 0.0) -> float:  # noqa: D102
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

    def step(self, net_return: float, turnover: float = 0.0) -> float:  # noqa: D102
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


# =========================================================================== #
# CANDIDATOS ABIERTOS EL 2026-09-19 TRAS EL DIAGNÓSTICO DE §7.11.
#
# NO SON BRAZOS DE D4 TODAVÍA. D4 dice "tres brazos y no más" y esa restricción
# sigue en pie: cada brazo que se ENTRENA degrada el Sharpe deflactado de D10.
# Lo que habilita tenerlos codificados es que ahora se pueden TAMIZAR SIN
# ENTRENAR (scripts/d4_diagnostico_recompensas.py): caracterizar una recompensa
# solo necesita series de retorno, no un agente. Solo el que pase el tamiz
# pre-registrado se lleva corridas — y ahí sí entra al contador.
#
# LOS TRES λ VAN SIN DEFECTO A PROPÓSITO. Un λ inventado que nadie recalibra
# cuando cambia el universo es exactamente la trampa que este proyecto ya pisó
# tres veces. Se calculan con `calibra_escala()` y se pre-registran.
# =========================================================================== #


class MeanVariance(Reward):
    """C1 — log-retorno neto MENOS λ·(desviación)². Es D4(a), la propuesta del
    2026-09-02 que la reunión bajó a brazo de sensibilidad.

        r_t = log(1+R_t) − λ·(R_t − A_{t-1})²

    POR QUÉ VUELVE A LA MESA, Y NO ES NOSTALGIA. §7.11 midió que el precio que
    el DSR le pone a la varianza vale A/(2B) —proporcional a la media móvil del
    retorno—, con lo cual pesa 7-10% de la señal y en 44% de los días de
    entrenamiento sale NEGATIVO. Acá el precio del riesgo es λ: una CONSTANTE
    pre-registrada. Pierde la ventaja de "un parámetro menos" que ganó el DSR y
    gana que el término de riesgo no degenere cuando el mercado no tiene deriva.
    """

    name = "mv"

    def __init__(self, lam: float | None = None, eta: float = 1.0 / 60.0) -> None:
        if lam is None:
            raise ValueError(
                "MeanVariance necesita lam EXPLÍCITO. Se calibra con "
                "scripts/d4_diagnostico_recompensas.py::calibra_escala y se "
                "pre-registra; no se ajusta contra resultados."
            )
        self.lam = float(lam)
        self.eta = float(eta)
        self.reset()

    def reset(self) -> None:  # noqa: D102
        self.a = 0.0
        self.m2 = 0.0
        self.n = 0

    def step(self, net_return: float, turnover: float = 0.0) -> float:  # noqa: D102
        r = float(net_return)
        dev = r - self.a
        recompensa = float(np.log1p(max(r, -0.999999))) - self.lam * dev * dev
        self.a += self.eta * (r - self.a)
        self.m2 += self.eta * (dev * dev - self.m2)
        self.n += 1
        return float(recompensa)

    def state(self) -> np.ndarray:  # noqa: D102
        return np.array([self.a * 100.0, np.sqrt(max(self.m2, 0.0)) * 100.0],
                        dtype=np.float32)


class LogReturnDrawdown(Reward):
    """C2 — log-retorno neto MENOS λ·(lo que se PROFUNDIZA el drawdown).

        DD_t = 1 − V_t / max_{s<=t} V_s
        r_t  = log(1+R_t) − λ·max(0, DD_t − DD_{t-1})

    POR QUÉ ESTE Y NO OTRO. La ventaja MEDIDA del agente contra el 1/N no es el
    retorno: es el drawdown (§7.7: mejor en los tres pliegues, la mitad en el de
    pandemia). Una recompensa que premia lo que el agente ya hace bien es la
    única de la lista con una hipótesis previa a favor, y no sale de la
    intuición sino del registro de corridas.

    MARKOV. El drawdown es path-dependent, que es justo lo que D4 usó para
    DESCARTAR el drawdown máximo como recompensa. La objeción se levanta igual
    que con el DSR: el estado suficiente —DD_t— se expone en `state()` y el
    entorno lo concatena a la observación. Se penaliza el INCREMENTO y no el
    nivel para que la señal no sea una constante arrastrada.

    Es la forma por paso del objetivo tipo Calmar / E(MDD) de Almahdi y Yang
    (2017), que sobre el S&P100 rinde una frontera mejor que la de Sharpe. No se
    copia su métrica terminal: una métrica terminal no da señal por paso.
    """

    name = "logret_dd"

    def __init__(self, lam: float | None = None) -> None:
        if lam is None:
            raise ValueError(
                "LogReturnDrawdown necesita lam EXPLÍCITO (ver calibra_escala)."
            )
        self.lam = float(lam)
        self.reset()

    def reset(self) -> None:  # noqa: D102
        self.v = 1.0
        self.pico = 1.0
        self.dd = 0.0
        self.n = 0

    def step(self, net_return: float, turnover: float = 0.0) -> float:  # noqa: D102
        r = float(net_return)
        self.v *= 1.0 + r
        self.pico = max(self.pico, self.v)
        dd_nuevo = 1.0 - self.v / self.pico
        castigo = max(0.0, dd_nuevo - self.dd)
        self.dd = dd_nuevo
        self.n += 1
        return float(np.log1p(max(r, -0.999999)) - self.lam * castigo)

    def state(self) -> np.ndarray:  # noqa: D102
        return np.array([self.dd * 100.0], dtype=np.float32)


class DSRTurnover(Reward):
    """C3 — DSR MENOS κ·rotación. REABRE D7, y por eso lleva esta nota larga.

    D7 dice que no se pone penalizador de rotación además del costo porque
    "sería cobrar dos veces". El argumento es bueno y sigue siéndolo SI las dos
    cosas hablan en la misma escala. §7.11 muestra que no: el costo entra dentro
    de R_t, que a escala diaria vale ~1e-3, y el DSR lo multiplica por
    B/V^{3/2}, que en tramos calmos se dispara. El peaje no desaparece — queda
    sumergido bajo un factor que el agente puede mover.

    ESTA NO ES UNA SEGUNDA COBRANZA: es la MISMA cobranza expresada en unidades
    de recompensa. Si se pre-registra κ = tasa_de_costo·B/V^{3/2} local, el
    castigo equivale al costo que ya se pagó, medido con la vara con la que el
    agente lee todo lo demás. Con κ fijo sí se vuelve una segunda cobranza y hay
    que decirlo: por eso el brazo se llama "reabre D7" y no "corrige D7".
    """

    name = "dsr_rot"

    def __init__(self, kappa: float | None = None, eta: float = 1.0 / 60.0,
                 escala_local: bool = True) -> None:
        if kappa is None:
            raise ValueError(
                "DSRTurnover necesita kappa EXPLÍCITO (ver calibra_escala)."
            )
        self.kappa = float(kappa)
        self.eta = float(eta)
        self.escala_local = bool(escala_local)
        self._dsr = DifferentialSharpe(eta=eta)
        self.reset()

    def reset(self) -> None:  # noqa: D102
        self._dsr.reset()
        self.ultimo_castigo = 0.0
        self.n = 0

    def step(self, net_return: float, turnover: float = 0.0) -> float:  # noqa: D102
        # El factor se toma ANTES de actualizar, igual que el propio DSR: es el
        # estado del paso anterior, que es lo que el agente pudo observar.
        b, a = self._dsr.b, self._dsr.a
        var = b - a * a
        factor = b / var ** 1.5 if var > _EPS else 0.0
        base = self._dsr.step(net_return)
        castigo = self.kappa * float(turnover) * (factor if self.escala_local else 1.0)
        self.ultimo_castigo = castigo
        self.n += 1
        return float(base - castigo)

    def state(self) -> np.ndarray:  # noqa: D102
        return self._dsr.state()


REWARDS: dict[str, type[Reward]] = {
    "dsr": DifferentialSharpe,
    "ddr": DifferentialDownside,
    "logret": NetLogReturn,
    # candidatos en TAMIZ, no brazos adoptados (ver el bloque de arriba)
    "mv": MeanVariance,
    "logret_dd": LogReturnDrawdown,
    "dsr_rot": DSRTurnover,
}


def make_reward(name: str, **kwargs) -> Reward:
    """Fábrica por nombre, para que el brazo del experimento sea un string."""
    if name not in REWARDS:
        raise KeyError(f"recompensa desconocida: {name!r}. Opciones: {sorted(REWARDS)}")
    return REWARDS[name](**kwargs)
