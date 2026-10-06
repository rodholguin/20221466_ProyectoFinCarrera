"""OE1 — baselines como políticas DENTRO del mismo simulador (D10).

Decisión de diseño, y no es cosmética: los baselines NO se calculan aparte con
pandas. Corren en el mismo entorno, con el mismo modelo de costos, la misma
máscara de días sin negociación y la misma remuneración de la caja. Así la
comparación es exacta por construcción y no por revisión: si el entorno tiene un
sesgo, lo tienen los dos lados.

REQUISITO DE EQUIDAD (reunión 2026-09-02, A3): el especialista señaló que el 1/N
es "casi invencible" si no hay costos. Comparar contra un 1/N rebalanceado a
diario bajo 0.43% + spread sería ganarle a un baseline mal implementado, así que
cada baseline corre con SU PROPIA frecuencia de rebalanceo, elegida en
train/validación. Por eso `rebalance_every` es del entorno y no de la política.

Comprar y mantener no es una política aparte: es `EqualWeight` con
`rebalance_every` mayor que el episodio. Eso lo hace EXACTO (cero operaciones
después de la compra inicial) en vez de aproximado.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from .portfolio_env import PortfolioEnv


class Policy(ABC):
    """Política determinista o estocástica sobre el símplex de 8."""

    name: str = "base"

    def reset(self) -> None:
        return None

    @abstractmethod
    def act(self, obs: np.ndarray, env: PortfolioEnv) -> np.ndarray:
        """Devuelve PESOS (no logits): usar el entorno con action_mode='weights'."""


class EqualWeight(Policy):
    """1/N sobre los activos, sin caja. El rival difícil de verdad."""

    name = "1/N"

    def act(self, obs, env):  # noqa: D102
        w = np.zeros(env.n_slots)
        w[: env.n_assets] = 1.0 / env.n_assets
        return w


class CashOnly(Policy):
    """Todo en caja. Sirve para verificar la remuneración de D9."""

    name = "caja"

    def act(self, obs, env):  # noqa: D102
        w = np.zeros(env.n_slots)
        w[env.cash_slot] = 1.0
        return w


class FixedWeights(Policy):
    """Pesos fijos arbitrarios; base de la banda nula y de pruebas."""

    def __init__(self, weights: np.ndarray, name: str = "fijo") -> None:
        self.weights = np.asarray(weights, dtype=float)
        self.name = name

    def act(self, obs, env):  # noqa: D102
        return self.weights


class RandomDirichlet(Policy):
    """Una realización de la BANDA NULA de D10.

    1,000 carteras aleatorias con las mismas restricciones y los mismos costos
    dan la distribución de lo que consigue el azar en este universo. Si el
    agente cae dentro de la banda, no hay hallazgo.

    POR DEFECTO SORTEA UNA SOLA VEZ y mantiene ese objetivo (`resample_every=0`).
    La primera versión re-sorteaba cada 21 días y daba una mediana de −60%: eso
    no medía la suerte de la asignación, medía el costo de rotar la cartera
    entera doce veces al año. Un null mal armado es un rival de paja al revés —
    hace ver bien a cualquier cosa— así que el sorteo va en la ASIGNACIÓN y la
    frecuencia de rebalanceo la fija el entorno, igual que para todo baseline.

    `resample_every > 0` se conserva para el caso en que se quiera un null que
    también rote: es el comparable correcto SOLO si el agente rota parecido.
    """

    name = "aleatoria"

    def __init__(self, seed: int = 0, alpha: float = 1.0, resample_every: int = 0) -> None:
        self.rng = np.random.default_rng(seed)
        self.alpha = alpha
        self.resample_every = int(resample_every)
        self._w: np.ndarray | None = None
        self._k = 0

    def reset(self) -> None:  # noqa: D102
        self._w = None
        self._k = 0

    def act(self, obs, env):  # noqa: D102
        redibuja = self.resample_every > 0 and self._k % self.resample_every == 0
        if self._w is None or redibuja:
            self._w = self.rng.dirichlet(np.full(env.n_slots, self.alpha))
        self._k += 1
        return self._w


# --------------------------------------------------------------------------
# Markowitz (media-varianza) — el tercer baseline del documento de tesis
# --------------------------------------------------------------------------
class Markowitz(Policy):
    """Media-varianza clásica con ventana móvil, long-only (§2.2.4 del E3).

    ESTIMACIÓN CAUSAL, y es el punto delicado. La política se llama con el
    reloj del entorno en `e` (el día de EJECUCIÓN), y la observación que le
    corresponde se construyó con datos hasta el cierre de `e-1`. Así que la
    ventana de estimación termina en `e-1`: `prices[lo:env.t]`, cuyo último
    retorno es el de `e-2 -> e-1`. Mismo insumo que ve el agente, ni un día
    más. Un baseline que estimara con `prices[e]` estaría mirando su propio
    día de ejecución y le ganaría al agente por trampa, no por método.

    DOS OBJETIVOS, y el primero es el del documento:

      "tangencia"  máximo Sharpe sobre el símplex long-only. Es la
                   formulación clásica: usa retornos esperados Y covarianza.
      "min_var"    varianza mínima global. NO usa retornos esperados, así que
                   no es lo que pide §2.2.4; se incluye como brazo de
                   robustez porque la media muestral es el estimador
                   notoriamente inestable de los dos.

    EL CASO DEGENERADO NO ES UN DETALLE DE IMPLEMENTACIÓN — ES UNA DECISIÓN.
    Si NINGÚN activo tiene retorno esperado por encima de la tasa libre de
    riesgo, la cartera tangente long-only no existe (el problema queda
    infactible). En este universo eso pasa seguido: la caja le ganó a todo en
    2013-2025. La regla adoptada es IR A CAJA, que es la respuesta correcta de
    la teoría cuando el activo sin riesgo domina a todos los riesgosos, y es
    coherente con D9 y con que la evaluación tenga que poder premiar salirse
    del mercado. Se declara porque la alternativa —forzar la cartera menos
    mala— convertiría al baseline en un hombre de paja.

    ENCOGIMIENTO. Por defecto NO se encoge: esa es la formulación que
    compromete el documento. `shrinkage="ledoit_wolf"` activa el encogimiento
    hacia identidad escalada que D10 agregó como mitigación. Se reportan las
    DOS versiones; no se elige una mirando el resultado.

    SESGO CONOCIDO DE LA ESTIMACIÓN EN ESTE PANEL, y hay que decirlo: los
    precios arrastrados (`is_stale`, entre 24% y 44% de los días según el
    activo) producen retornos cero que DEFLACTAN la volatilidad estimada y
    diluyen las covarianzas. O sea el Markowitz de acá cree que el universo es
    menos riesgoso y menos correlacionado de lo que es. Es una propiedad de la
    BVL, no un defecto del código, y afecta igual a cualquiera que estime con
    estos precios.
    """

    def __init__(
        self,
        window: int = 252,
        objetivo: str = "tangencia",
        shrinkage: str | None = None,
        min_obs: int = 60,
        ridge: float = 1e-10,
        recompute_every: int | None = None,
        name: str | None = None,
    ) -> None:
        if objetivo not in ("tangencia", "min_var"):
            raise ValueError(f"objetivo desconocido: {objetivo!r}")
        if shrinkage not in (None, "ledoit_wolf"):
            raise ValueError(f"shrinkage desconocido: {shrinkage!r}")
        if min_obs < 2:
            raise ValueError("min_obs debe ser al menos 2 para estimar una covarianza")
        self.window = int(window)
        self.objetivo = objetivo
        self.shrinkage = shrinkage
        self.min_obs = int(min_obs)
        self.ridge = float(ridge)
        self.recompute_every = recompute_every
        sufijo = {"tangencia": "", "min_var": "-minvar"}[objetivo]
        sufijo += "-LW" if shrinkage else ""
        self.name = name or f"markowitz{sufijo}"
        self._w: np.ndarray | None = None
        #: cuántas veces el problema salió degenerado y se fue a caja. Es
        #: diagnóstico REPORTABLE, no ruido: dice qué fracción del horizonte
        #: la teoría clásica recomendó no estar en el mercado.
        self.n_degenerado = 0
        self.n_resueltos = 0

    def reset(self) -> None:  # noqa: D102
        self._w = None
        self.n_degenerado = 0
        self.n_resueltos = 0

    # ---------------------------------------------------------------- API
    def act(self, obs, env):  # noqa: D102
        cada = self.recompute_every or max(1, env.cfg.rebalance_every)
        if self._w is None or env.step_count % cada == 0:
            self._w = self._resolver(env)
        return self._w

    # ----------------------------------------------------------- internos
    def _a_caja(self, env) -> np.ndarray:
        w = np.zeros(env.n_slots)
        w[env.cash_slot] = 1.0
        return w

    def _resolver(self, env) -> np.ndarray:
        self.n_resueltos += 1
        lo = max(0, env.t - self.window - 1)
        px = env.panel.prices[lo : env.t]  # cierres hasta e-1 INCLUSIVE
        if px.shape[0] < self.min_obs + 1:
            # Sin historia suficiente no se inventa una covarianza: se espera
            # en caja. Con el calentamiento de D6 (250d) esto no debería
            # dispararse nunca en el panel real; está por si alguien mueve t0.
            self.n_degenerado += 1
            return self._a_caja(env)

        rets = px[1:] / px[:-1] - 1.0
        cov = self._covarianza(rets)
        cov = cov + self.ridge * np.eye(cov.shape[0])

        if self.objetivo == "min_var":
            w_act = _min_var_long_only(cov)
        else:
            rf = float(np.mean(env.panel.rf_daily[lo + 1 : env.t]))
            w_act = _tangencia_long_only(rets.mean(axis=0) - rf, cov)

        if w_act is None:
            self.n_degenerado += 1
            return self._a_caja(env)

        w = np.zeros(env.n_slots)
        w[: env.n_assets] = w_act
        return w

    def _covarianza(self, rets: np.ndarray) -> np.ndarray:
        if self.shrinkage == "ledoit_wolf":
            return ledoit_wolf_cov(rets)
        return np.cov(rets, rowvar=False, ddof=1)


def ledoit_wolf_cov(rets: np.ndarray) -> np.ndarray:
    """Encogimiento de Ledoit-Wolf (2004) hacia identidad escalada.

    Se implementa acá en vez de importar scikit-learn por una razón concreta:
    scikit-learn no está en requirements.txt y una matriz de 7x7 no justifica
    una dependencia nueva. `tests/test_markowitz.py` contrasta esta salida
    contra `sklearn.covariance.ledoit_wolf` cuando está instalado, así que la
    equivalencia se verifica en vez de suponerse.

        Sigma = alpha * (tr(S)/n) * I + (1 - alpha) * S
    """
    x = np.asarray(rets, dtype=float)
    x = x - x.mean(axis=0)
    n_obs, n = x.shape
    if n_obs < 2:
        raise ValueError("Ledoit-Wolf necesita al menos 2 observaciones")

    s = (x.T @ x) / n_obs  # covarianza sesgada (1/T), como en el paper
    m = float(np.trace(s)) / n
    d2 = float(np.sum((s - m * np.eye(n)) ** 2)) / n
    if d2 <= 0:
        return s
    # sum_k ||x_k x_k' - S||_F^2  =  sum_k ||x_k||^4 - T ||S||_F^2
    b2 = (float(np.sum(np.sum(x**2, axis=1) ** 2)) - n_obs * float(np.sum(s**2))) / n
    b2 = b2 / (n_obs**2)
    alpha = min(max(b2 / d2, 0.0), 1.0)
    return alpha * m * np.eye(n) + (1.0 - alpha) * s


def _min_var_long_only(cov: np.ndarray) -> np.ndarray:
    """min w'Sw  s.a.  sum(w) = 1,  w >= 0."""
    from scipy.optimize import minimize

    n = cov.shape[0]
    w0 = np.full(n, 1.0 / n)
    res = minimize(
        lambda w: float(w @ cov @ w),
        w0,
        jac=lambda w: 2.0 * cov @ w,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n,
        constraints=({"type": "eq", "fun": lambda w: w.sum() - 1.0},),
        options={"maxiter": 300, "ftol": 1e-14},
    )
    w = np.clip(np.asarray(res.x, dtype=float), 0.0, None)
    s = w.sum()
    return w / s if s > 0 and np.all(np.isfinite(w)) else w0


def _tangencia_long_only(mu_exceso: np.ndarray, cov: np.ndarray) -> np.ndarray | None:
    """Cartera tangente long-only, o None si el problema es degenerado.

    TRUCO ESTÁNDAR que evita optimizar un cociente (el Sharpe no es convexo,
    pero esto sí): se resuelve

        min y'Sy   s.a.   mu_exceso' y = 1,   y >= 0

    y se normaliza w = y / sum(y). La restricción es factible si y solo si
    ALGÚN mu_exceso es positivo — que es exactamente la condición de
    existencia de la cartera tangente long-only. Por eso el chequeo de abajo
    no es una salvaguarda defensiva: es la condición del problema.
    """
    from scipy.optimize import minimize

    mu_exceso = np.asarray(mu_exceso, dtype=float)
    if not np.any(mu_exceso > 0) or not np.all(np.isfinite(mu_exceso)):
        return None

    n = len(mu_exceso)
    y0 = np.where(mu_exceso > 0, mu_exceso, 0.0)
    denom = float(mu_exceso @ y0)
    y0 = y0 / denom if denom > 0 else np.full(n, 1.0 / n)
    res = minimize(
        lambda y: float(y @ cov @ y),
        y0,
        jac=lambda y: 2.0 * cov @ y,
        method="SLSQP",
        bounds=[(0.0, None)] * n,
        constraints=({"type": "eq", "fun": lambda y: float(mu_exceso @ y) - 1.0},),
        options={"maxiter": 500, "ftol": 1e-16},
    )
    y = np.clip(np.asarray(res.x, dtype=float), 0.0, None)
    s = y.sum()
    if s <= 0 or not np.all(np.isfinite(y)):
        return None
    return y / s


def run_policy(env: PortfolioEnv, policy: Policy) -> dict:
    """Corre una política de punta a punta y devuelve historia + métricas."""
    if env.cfg.action_mode != "weights":
        raise ValueError(
            "los baselines emiten PESOS: construye el entorno con action_mode='weights'"
        )
    policy.reset()
    out = env.reset()
    obs = out[0] if isinstance(out, tuple) else out
    done = False
    while not done:
        action = policy.act(obs, env)
        res = env.step(action)
        if len(res) == 5:
            obs, _, terminated, truncated, _ = res
            done = terminated or truncated
        else:
            obs, _, done, _ = res
    return {
        "policy": policy.name,
        "equity": env.equity_curve,
        "returns": env.returns,
        "dates": np.asarray(env.history["date"]),
        "weights": np.asarray(env.history["weights"]),
        "summary": env.summary(),
    }
