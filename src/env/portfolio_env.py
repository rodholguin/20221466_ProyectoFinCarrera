"""OE1 — entorno de portafolio sobre la BVL (D1, D2, D8, D9, D13).

Un agente que observa el cierre de t y devuelve pesos objetivo que se EJECUTAN
al cierre de t+1 (D13). Long-only, sin apalancamiento, 7 activos más caja.

RELOJ DEL ENTORNO — es lo único que hay que tener claro para leer el resto:

    paso k:  observación construida con datos hasta el cierre de  e-1
             ejecución del rebalanceo al cierre de                e
             el portafolio gana el retorno de                     e -> e+1
             recompensa a partir de ese retorno NETO

    La observación que se entrega al final del paso k es la de `e`, y se
    ejecutará en `e+1`. Por construcción no existe forma de que una decisión
    use información de su propio día de ejecución.

CURVA DE PATRIMONIO. Se registra V_pre(e) = valor marcado a mercado al cierre de
e ANTES de operar. Entonces V_pre(e+1) = V_post-trade(e) revaluado, y el retorno
del paso es

    R_k = V_pre(e+1) / V_pre(e) − 1

que incluye el costo de la operación (que redujo el valor) y el movimiento de
mercado. Eso es exactamente "retorno neto de costos" y hace que los tests de
conservación den EXACTO con costo cero.

CONTABILIDAD EN UNIDADES, NO EN PESOS. Se guardan unidades del índice de retorno
total; la deriva de los pesos con el precio sale sola y no hay que corregirla a
mano. `close_total_return` no es un precio transable sino un índice con
dividendos reinvertidos: se declara, y el nocional de las órdenes se mide en la
misma unidad monetaria que el patrimonio inicial.

D2 — ACCIÓN. Vector de 8 (7 activos + caja) sobre el símplex. El activo
enmascarado CONSERVA su peso y el agente reparte solo el presupuesto remanente:
la renormalización es sobre el remanente, no sobre el total.

D8 — MÁSCARA DURA en `is_no_trade` ("si nadie quiere jugar, no juega"). No se
penaliza un intento imposible: se impide. `is_stale` NO prohíbe: encarece, vía
`stale_surcharge_bps` del modelo de costos.

D9 — la caja RINDE. Si rinde cero mientras la tasa de referencia no lo hace, el
entorno castiga estructuralmente al agente por defenderse.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from .costs import CostModel, zero_cost_model
from .panel import PanelData
from .rewards import Reward, make_reward

try:  # gymnasium es opcional: el entorno y los tests corren sin él.
    import gymnasium as gym
    from gymnasium import spaces

    _GYM = True
except ImportError:  # pragma: no cover - depende del entorno de ejecución
    gym = None
    spaces = None
    _GYM = False

_BASE = gym.Env if _GYM else object

#: Piso de ruido de un retorno diario. El retorno de un paso sale de dividir dos
#: patrimonios de ~1e6, así que su error relativo es ~1e-16: cualquier
#: desviación por debajo de esto es coma flotante, no economía. Ver
#: `PortfolioEnv.summary`, que sin esto devolvía un Sortino de -14.99 para una
#: cartera 100% en caja (un 0/0 disfrazado).
_RUIDO_RETORNO = 1e-12


@dataclass
class EnvConfig:
    """Parámetros del entorno. Todo lo que un brazo del experimento cambiaría."""

    initial_capital: float = 1_800_000.0  # ~S/1.8 MM, capacidad acotada por BCP
    reward: str = "dsr"  # dsr | ddr | logret  (D4)
    reward_kwargs: dict[str, Any] = field(default_factory=dict)
    rebalance_every: int = 1  # 1 = decisión diaria (D21/F)
    band_notional: float | None = None  # None -> se deriva del mínimo por orden
    # "delta"   la acción es un AJUSTE sobre los pesos actuales (D2 enmendada).
    #           Es el modo de producción: a = 0 significa NO OPERAR, y ese
    #           estado es alcanzable y barato en vez de ser un accidente.
    # "logits"  la acción es el vector de pesos objetivo, vía softmax. Modo
    #           original; se conserva como brazo de comparación.
    # "weights" la acción YA son pesos. Para baselines y tests.
    action_mode: Literal["delta", "logits", "weights"] = "delta"
    # Desplazamiento máximo por activo y por paso, en fracción del portafolio.
    # 0.05 = 5 pp. No es un botón de desempeño: acota cuánto puede moverse la
    # cartera en un día, que es una restricción de mandato, no una preferencia.
    action_scale: float = 0.05
    max_cash_weight: float = 1.0  # 1.0 permite salirse del mercado por completo
    start_index: int | None = None  # por defecto, tras el calentamiento de D6
    # Fin del tramo (exclusivo). Se usa para recortar a un pliegue del
    # walk-forward SIN volver a cargar el panel: la normalización causal de D6
    # tiene que acumular desde el principio del historial, así que recortar por
    # fechas al cargar reiniciaría las estadísticas y cambiaría las features.
    end_index: int | None = None
    # Solo para ENTRENAR. Con una única trayectoria histórica, arrancar siempre
    # el mismo día produce rollouts idénticos y la política sobreajusta el tramo
    # inicial. Sortear el arranque decorrelaciona sin inventar datos. En
    # evaluación va SIEMPRE en False: el episodio tiene que ser el tramo entero.
    random_start: bool = False
    min_episode_len: int = 252


class PortfolioEnv(_BASE):
    """Entorno Gymnasium de asignación de portafolio sobre el panel de R6."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        panel: PanelData,
        cost_model: CostModel | None = None,
        config: EnvConfig | None = None,
    ) -> None:
        self.panel = panel
        self.cfg = config or EnvConfig()
        self.costs = cost_model or zero_cost_model(panel.tickers)
        if list(self.costs.tickers) != list(panel.tickers):
            raise ValueError("el modelo de costos y el panel tienen distinto orden de activos")

        self.n_assets = panel.n_assets
        self.n_slots = self.n_assets + 1  # + caja
        self.cash_slot = self.n_assets

        self.reward_fn: Reward = make_reward(self.cfg.reward, **self.cfg.reward_kwargs)

        band = self.cfg.band_notional
        self.band = self.costs.band_notional() if band is None else float(band)

        warmup = panel.features.warmup
        first = warmup + 1 if self.cfg.start_index is None else int(self.cfg.start_index)
        # Nunca antes de que TODOS los activos coticen: no se puede tener lo que
        # no está listado (InRetail sale a bolsa en 2012-10).
        self.t_min = max(1, first, panel.first_tradable_index)
        self.t0 = self.t_min  # arranque del episodio en curso (ver random_start)
        fin = panel.n_steps if self.cfg.end_index is None else int(self.cfg.end_index)
        self.t_last = min(panel.n_steps, fin) - 2  # hace falta P(e+1)
        self._rng = np.random.default_rng()
        if self.t0 > self.t_last:
            raise ValueError(
                f"tramo demasiado corto: t0={self.t0} > t_last={self.t_last}. "
                "Revisa el recorte temporal o el calentamiento de D6."
            )

        obs_dim = panel.features.flat_dim() + self.n_slots + self.reward_fn.state_dim
        self._obs_dim = obs_dim
        if _GYM:
            self.observation_space = spaces.Box(
                low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32
            )
            self.action_space = spaces.Box(
                low=-10.0, high=10.0, shape=(self.n_slots,), dtype=np.float32
            )

        self.reset()

    # ------------------------------------------------------------------ API
    def reset(self, *, seed: int | None = None, options=None):  # noqa: D102
        if seed is not None:
            self._rng = np.random.default_rng(seed)
            if _GYM:
                super().reset(seed=seed)
        self.t0 = self.t_min
        if self.cfg.random_start:
            tope = self.t_last - self.cfg.min_episode_len
            if tope > self.t_min:
                self.t0 = int(self._rng.integers(self.t_min, tope))
        self.t = self.t0
        self.step_count = 0
        self.units = np.zeros(self.n_assets, dtype=float)
        self.cash = float(self.cfg.initial_capital)
        self.reward_fn.reset()

        v0 = self._value(self.t)
        self.w_post = self._weights(self.t)
        self.history: dict[str, list] = {
            "date": [self.panel.dates[self.t]],
            "equity": [v0],
            "net_return": [],
            "cost": [],
            "turnover": [],
            "weights": [self.w_post.copy()],
        }
        obs = self._observation(self.t - 1)
        return (obs, {}) if _GYM else obs

    def step(self, action):  # noqa: D102
        e = self.t
        v_pre = self._value(e)
        if v_pre <= 0:
            raise RuntimeError("el portafolio quedó sin valor; revisa el modelo de costos")

        target = self._resolve_target(action, e, v_pre)
        cost, turnover = self._execute(target, e, v_pre)

        # --- avance de e a e+1: la caja rinde exactamente un día (D9) ---
        self.cash *= 1.0 + self.panel.rf_daily[e]
        self.t = e + 1
        v_next = self._value(self.t)

        net_return = v_next / v_pre - 1.0
        reward = self.reward_fn.step(net_return)

        self.step_count += 1
        self.w_post = target
        self.history["date"].append(self.panel.dates[self.t])
        self.history["equity"].append(v_next)
        self.history["net_return"].append(net_return)
        self.history["cost"].append(cost)
        self.history["turnover"].append(turnover)
        self.history["weights"].append(target.copy())

        terminated = False
        truncated = self.t >= self.t_last + 1
        obs = self._observation(self.t - 1)
        info = {
            "equity": v_next,
            "net_return": net_return,
            "cost": cost,
            "turnover": turnover,
            "weights": target.copy(),
            "date": self.panel.dates[self.t],
        }
        if _GYM:
            return obs, float(reward), terminated, truncated, info
        return obs, float(reward), truncated, info

    # -------------------------------------------------------------- internos
    def _value(self, idx: int) -> float:
        return float(self.units @ self.panel.prices[idx] + self.cash)

    def _weights(self, idx: int) -> np.ndarray:
        v = self._value(idx)
        w = np.zeros(self.n_slots, dtype=float)
        if v <= 0:
            w[self.cash_slot] = 1.0
            return w
        w[: self.n_assets] = self.units * self.panel.prices[idx] / v
        w[self.cash_slot] = self.cash / v
        return w

    def _raw_target(self, action, w_cur: np.ndarray) -> np.ndarray:
        a = np.asarray(action, dtype=float).reshape(-1)
        if a.shape[0] != self.n_slots:
            raise ValueError(f"la acción debe tener {self.n_slots} componentes, llegaron {a.shape[0]}")

        if self.cfg.action_mode == "delta":
            # D2 ENMENDADA: la acción desplaza la cartera, no la redefine.
            # a = 0 devuelve w_cur EXACTAMENTE (la suma ya vale 1, así que la
            # renormalización es la identidad) -> "no operar" es alcanzable.
            w = np.clip(w_cur + self.cfg.action_scale * np.tanh(a), 0.0, None)
            s = w.sum()
            return w / s if s > 0 else w_cur.copy()

        if self.cfg.action_mode == "weights":
            a = np.clip(a, 0.0, None)
            s = a.sum()
            return a / s if s > 0 else np.full(self.n_slots, 1.0 / self.n_slots)

        z = a - a.max()
        ex = np.exp(z)
        return ex / ex.sum()

    def _resolve_target(self, action, e: int, v_pre: float) -> np.ndarray:
        """Aplica máscara (D8), tope de caja, banda (D7) y devuelve pesos objetivo."""
        w_cur = self._weights(e)

        rebalancing = self.step_count % max(1, self.cfg.rebalance_every) == 0
        if not rebalancing:
            return w_cur

        raw = self._raw_target(action, w_cur)
        masked = self.panel.no_trade[e]

        # --- D2/D8: lo enmascarado se congela; el resto reparte el remanente ---
        target = w_cur.copy()
        frozen = float(w_cur[: self.n_assets][masked].sum())
        free_slots = np.ones(self.n_slots, dtype=bool)
        free_slots[: self.n_assets] = ~masked  # la caja SIEMPRE es libre

        budget = max(0.0, 1.0 - frozen)
        free_raw = raw[free_slots]
        s = free_raw.sum()
        free_target = (free_raw / s) * budget if s > 0 else np.full(free_slots.sum(), budget / free_slots.sum())
        target[free_slots] = free_target

        # --- tope de caja (permite exigir estar invertido, si algún día se quiere) ---
        if self.cfg.max_cash_weight < 1.0 and target[self.cash_slot] > self.cfg.max_cash_weight:
            exceso = target[self.cash_slot] - self.cfg.max_cash_weight
            libres = free_slots.copy()
            libres[self.cash_slot] = False
            s2 = target[libres].sum()
            if s2 > 0:
                target[libres] += exceso * target[libres] / s2
                target[self.cash_slot] = self.cfg.max_cash_weight

        # --- D7: banda de no-operación, derivada del mínimo por orden ---
        if self.band > 0:
            for i in range(self.n_assets):
                if masked[i]:
                    continue
                if abs(target[i] - w_cur[i]) * v_pre < self.band:
                    target[i] = w_cur[i]

        # la caja absorbe el residuo; si no alcanza, se escalan los activos libres
        suma_activos = float(target[: self.n_assets].sum())
        if suma_activos > 1.0:
            libres = ~masked
            exceso = suma_activos - 1.0
            val_libres = float(target[: self.n_assets][libres].sum())
            if val_libres > 0:
                escala = max(0.0, (val_libres - exceso) / val_libres)
                target[: self.n_assets][libres] *= escala
            suma_activos = float(target[: self.n_assets].sum())
        target[self.cash_slot] = 1.0 - suma_activos
        return target

    def _execute(self, target: np.ndarray, e: int, v_pre: float) -> tuple[float, float]:
        """Convierte pesos objetivo en unidades, cobrando el costo. Devuelve (costo, rotación)."""
        prices = self.panel.prices[e]
        val_cur = self.units * prices
        val_tgt = target[: self.n_assets] * v_pre
        masked = self.panel.no_trade[e]

        # Ruido de coma flotante NO es una orden. Sin este ajuste, una diferencia
        # de 1e-16 dispararía la comisión MÍNIMA (S/40) por activo y por día.
        tol = 1e-8 * v_pre
        val_tgt = np.where(np.abs(val_tgt - val_cur) < tol, val_cur, val_tgt)

        cost = 0.0
        # Dos pasadas: el costo sale de la caja y, si no alcanza, se reducen los
        # activos LIBRES (nunca los enmascarados, que por D8 no se pueden tocar).
        for _ in range(2):
            notionals = np.abs(val_tgt - val_cur)
            notionals[masked] = 0.0
            cost = float(self.costs.cost_of_trades(notionals, e, self.panel.stale[e]).sum())
            cash_after = v_pre - float(val_tgt.sum()) - cost
            if cash_after >= 0.0:
                break
            libres = ~masked
            val_libres = float(val_tgt[libres].sum())
            if val_libres <= 0:
                break
            escala = max(0.0, (val_libres + cash_after) / val_libres)
            val_tgt[libres] *= escala

        notionals = np.abs(val_tgt - val_cur)
        notionals[masked] = 0.0
        turnover = float(notionals.sum() / v_pre) if v_pre > 0 else 0.0

        nuevas = val_tgt / prices
        # D8 al pie de la letra: lo enmascarado no se toca, ni siquiera por
        # redondeo. Se copia la unidad anterior en vez de recalcularla.
        nuevas[masked] = self.units[masked]
        self.units = nuevas
        self.cash = v_pre - float(val_tgt.sum()) - cost
        if self.cash < -1e-6:
            raise RuntimeError(f"caja negativa tras ejecutar ({self.cash:.6f}); revisa el costo")
        self.cash = max(self.cash, 0.0)
        return cost, turnover

    def _observation(self, idx: int) -> np.ndarray:
        feats = self.panel.features.values[idx].reshape(-1)
        return np.concatenate(
            [feats, self.w_post.astype(np.float32), self.reward_fn.state()]
        ).astype(np.float32)

    # ------------------------------------------------------------- utilidades
    @property
    def equity_curve(self) -> np.ndarray:
        return np.asarray(self.history["equity"], dtype=float)

    @property
    def returns(self) -> np.ndarray:
        return np.asarray(self.history["net_return"], dtype=float)

    def summary(self) -> dict[str, float]:
        """Métricas del episodio, en el conjunto que fija §2.2.6 del documento.

        Sharpe (principal), Sortino, máximo drawdown, retorno acumulado,
        retorno ANUALIZADO y volatilidad anualizada. Las de D10 —Sharpe
        deflactado, bootstrap por bloques, banda nula— viven en la evaluación,
        no acá: dependen del CONJUNTO de corridas, no de una sola.

        DOS CONVENCIONES QUE HAY QUE DECLARAR, porque cambian el número:

        (a) EL UMBRAL DEL SORTINO ES LA TASA LIBRE DE RIESGO, no cero. Es la
            misma referencia que usa el Sharpe de arriba, así que las dos
            métricas responden la misma pregunta y solo cambian el castigo a
            la dispersión. Con umbral cero, el Sortino de la caja sería
            infinito y el de cualquier estrategia defensiva quedaría inflado.
        (b) DESVIACIÓN A LA BAJA SOBRE TODOS LOS DÍAS (n en el denominador),
            no solo los días malos. Es la definición de Sortino-Satchell y la
            que hace comparables dos estrategias con distinta frecuencia de
            pérdidas; dividir entre el número de días negativos premiaría a
            quien pierde poco seguido.

        Si NUNCA hay retorno por debajo del umbral, el Sortino no está
        definido (denominador cero) y se devuelve 0.0, la misma convención
        que ya usa el Sharpe cuando la volatilidad es cero. Es el caso de
        `CashOnly`, cuyo Sharpe es 0.00 por construcción.

        POR QUÉ HAY UNA TOLERANCIA Y NO ES PARANOIA. `CashOnly` gana
        EXACTAMENTE la tasa libre de riesgo, así que su exceso y su
        desviación a la baja son cero EN ÁLGEBRA pero ~1e-17 en coma
        flotante: el retorno del paso sale de dividir dos patrimonios de
        ~1e6, no de leer la tasa. Sin la tolerancia el Sortino de la caja es
        un 0/0 disfrazado y devuelve basura con pinta de resultado — se midió
        −14.99 sobre el panel real. Se anulan las desviaciones por debajo del
        ruido de esa división, y el exceso se calcula a partir de LAS MISMAS
        desviaciones para que numerador y denominador sean consistentes.
        """
        r = self.returns
        eq = self.equity_curve
        if r.size == 0:
            return {}
        ann = 252.0
        vol = float(r.std(ddof=1)) * np.sqrt(ann)
        rf_diaria = self.panel.rf_daily[self.t0 : self.t]
        # Desviación contra la tasa libre de riesgo DEL DÍA, no contra su
        # promedio: la tasa del BCRP se mueve de 0.25% a 7.75% en el horizonte,
        # y usar el promedio mediría contra un umbral que no existió.
        desv = r - rf_diaria
        desv[np.abs(desv) < _RUIDO_RETORNO] = 0.0
        exceso = float(desv.mean()) * ann
        bajo_umbral = np.minimum(desv, 0.0)
        dd_anual = float(np.sqrt(np.mean(bajo_umbral**2))) * np.sqrt(ann)
        pico = np.maximum.accumulate(eq)
        # §2.2.6: R_anual = (V_final / V_inicial)^(252/n) - 1
        retorno_anual = float((eq[-1] / eq[0]) ** (ann / r.size) - 1.0)
        return {
            "retorno_total": float(eq[-1] / eq[0] - 1.0),
            "retorno_anualizado": retorno_anual,
            "vol_anual": vol,
            "sharpe": exceso / vol if vol > 0 else 0.0,
            "sortino": exceso / dd_anual if dd_anual > 0 else 0.0,
            "downside_dev_anual": dd_anual,
            "max_drawdown": float((eq / pico - 1.0).min()),
            "rotacion_anual": float(np.mean(self.history["turnover"])) * ann,
            "costo_total": float(np.sum(self.history["cost"])),
            "dias": int(r.size),
        }
