"""Tests de conservación del entorno de OE1.

Estos cuatro primeros son los que valen: la contabilidad es donde se meten los
bugs silenciosos, y un bug silencioso acá contamina TODOS los resultados de la
tesis sin hacer fallar nada.

    1. Con costo cero, "comprar y no tocar" replica EXACTAMENTE comprar y mantener.
    2. Con costo cero, 1/N diario replica EXACTAMENTE el 1/N calculado aparte.
    3. Todo en caja crece EXACTAMENTE a la tasa libre de riesgo compuesta (D9).
    4. Los pesos suman 1 y son no negativos en todo paso, también con la máscara
       activa, y las unidades de un activo enmascarado NO cambian (D8).

Corre con pytest o directo:  python tests/test_portfolio_env.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.env.costs import CostModel, zero_cost_model
from src.env.features import FeatureTensor
from src.env.panel import PanelData
from src.env.policies import CashOnly, EqualWeight, run_policy
from src.env.portfolio_env import EnvConfig, PortfolioEnv
from src.env.rewards import DifferentialDownside, DifferentialSharpe

RF_ANUAL = 0.0425  # como el `macro_tasa_ref` real del panel (4.25%)


# --------------------------------------------------------------------------
# panel sintético: determinista, sin depender del parquet de R6
# --------------------------------------------------------------------------
def panel_sintetico(
    n_dias: int = 80,
    n_activos: int = 3,
    seed: int = 7,
    no_trade: np.ndarray | None = None,
) -> PanelData:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0004, 0.012, size=(n_dias, n_activos))
    precios = 100.0 * np.cumprod(1.0 + rets, axis=0)
    fechas = np.array(
        [np.datetime64("2020-01-01") + np.timedelta64(i, "D") for i in range(n_dias)]
    )
    tickers = [f"A{i}" for i in range(n_activos)]
    feats = FeatureTensor(
        values=rng.normal(size=(n_dias, n_activos, 4)).astype(np.float32),
        columns=["f0", "f1", "f2", "f3"],
        tickers=tickers,
        warmup=0,
    )
    return PanelData(
        dates=fechas,
        tickers=tickers,
        prices=precios,
        no_trade=np.zeros((n_dias, n_activos), dtype=bool) if no_trade is None else no_trade,
        stale=np.zeros((n_dias, n_activos), dtype=bool),
        rf_daily=np.full(n_dias, RF_ANUAL / 365.0),
        features=feats,
    )


def _env(panel, **cfg) -> PortfolioEnv:
    base = dict(action_mode="weights", band_notional=0.0)
    base.update(cfg)
    return PortfolioEnv(panel, zero_cost_model(panel.tickers), EnvConfig(**base))


# --------------------------------------------------------------------------
# 1. comprar y mantener
# --------------------------------------------------------------------------
def test_buy_and_hold_exacto():
    p = panel_sintetico()
    # "comprar y mantener" no es una política aparte: es 1/N con una frecuencia
    # de rebalanceo mayor que el episodio. Así son CERO operaciones, no ~cero.
    env = _env(p, rebalance_every=10**9)
    res = run_policy(env, EqualWeight())

    t0 = env.t0
    v0 = env.cfg.initial_capital
    unidades = (v0 / p.n_assets) / p.prices[t0]
    esperado = np.concatenate([[v0], unidades @ p.prices[t0 + 1 : env.t + 1].T])

    assert np.allclose(res["equity"], esperado, rtol=1e-12, atol=1e-6), (
        "comprar y mantener no replica la valuación directa de las unidades"
    )
    assert np.allclose(env.history["turnover"][1:], 0.0), "hubo operaciones después de la compra"


# --------------------------------------------------------------------------
# 2. equiponderado diario
# --------------------------------------------------------------------------
def test_equiponderado_diario_exacto():
    p = panel_sintetico()
    env = _env(p, rebalance_every=1)
    res = run_policy(env, EqualWeight())

    t0, tf = env.t0, env.t
    ratios = p.prices[t0 + 1 : tf + 1] / p.prices[t0:tf]
    esperado = env.cfg.initial_capital * np.concatenate([[1.0], np.cumprod(ratios.mean(axis=1))])

    assert np.allclose(res["equity"], esperado, rtol=1e-11, atol=1e-6), (
        "el 1/N del entorno no coincide con el 1/N calculado fuera"
    )


# --------------------------------------------------------------------------
# 3. la caja rinde (D9)
# --------------------------------------------------------------------------
def test_caja_rinde_exacto():
    p = panel_sintetico()
    env = _env(p, rebalance_every=1)
    res = run_policy(env, CashOnly())

    t0, tf = env.t0, env.t
    factores = 1.0 + p.rf_daily[t0:tf]
    esperado = env.cfg.initial_capital * np.concatenate([[1.0], np.cumprod(factores)])

    assert np.allclose(res["equity"], esperado, rtol=1e-12), "la caja no rinde la rf compuesta"
    assert res["equity"][-1] > res["equity"][0], "la caja debería crecer con rf > 0"


# --------------------------------------------------------------------------
# 4. invariantes del símplex y de la máscara (D2, D8)
# --------------------------------------------------------------------------
def test_invariantes_simplex_y_mascara():
    rng = np.random.default_rng(3)
    n_dias, n_act = 80, 3
    mask = rng.random((n_dias, n_act)) < 0.35  # días sin negociación, abundantes
    p = panel_sintetico(n_dias=n_dias, n_activos=n_act, no_trade=mask)

    env = PortfolioEnv(
        p,
        CostModel(tickers=p.tickers, half_spread_bps=25.0, commission_rate=0.0043, min_fee=40.0),
        EnvConfig(action_mode="logits", rebalance_every=1, band_notional=0.0),
    )
    out = env.reset()
    obs = out[0] if isinstance(out, tuple) else out

    done = False
    while not done:
        e = env.t
        unidades_antes = env.units.copy()
        res = env.step(rng.normal(size=env.n_slots))
        obs = res[0]
        done = res[3] if len(res) == 5 and res[3] else (res[2] if len(res) == 4 else res[3])

        w = env.history["weights"][-1]
        assert abs(w.sum() - 1.0) < 1e-10, f"los pesos no suman 1: {w.sum()}"
        assert (w >= -1e-12).all(), "apareció un peso negativo (long-only violado)"
        assert env.cash >= -1e-9, "caja negativa: se coló apalancamiento"
        assert np.allclose(
            env.units[mask[e]], unidades_antes[mask[e]]
        ), "se operó un activo enmascarado (D8 violado)"
        assert env.equity_curve[-1] > 0, "el patrimonio se fue a cero o negativo"


# --------------------------------------------------------------------------
# 5. el costo resta, y la banda bloquea las órdenes chicas (D7)
# --------------------------------------------------------------------------
def test_costo_reduce_el_patrimonio():
    p = panel_sintetico()
    sin = _env(p, rebalance_every=1)
    r_sin = run_policy(sin, EqualWeight())

    con = PortfolioEnv(
        p,
        CostModel(tickers=p.tickers, half_spread_bps=110.0, commission_rate=0.0043, min_fee=40.0),
        EnvConfig(action_mode="weights", rebalance_every=1, band_notional=0.0),
    )
    r_con = run_policy(con, EqualWeight())

    assert r_con["equity"][-1] < r_sin["equity"][-1], "cobrar costo no redujo el patrimonio"
    assert sum(con.history["cost"]) > 0, "no se cobró ningún costo pese a haber rotación"


def test_banda_bloquea_ordenes_chicas():
    p = panel_sintetico()
    # Una banda mayor que el patrimonio bloquea TODO, incluida la compra inicial:
    # el agente se queda en caja. Es el comportamiento correcto, no un borde.
    env = _env(p, rebalance_every=1, band_notional=1e12)
    res = run_policy(env, EqualWeight())

    assert np.allclose(env.history["turnover"], 0.0), "la banda no bloqueó las operaciones"
    assert np.allclose(res["weights"][-1][env.cash_slot], 1.0), "no quedó todo en caja"


def test_banda_se_deriva_del_minimo_por_orden():
    # S/40 de mínimo con 0.43% de comisión => S/9,302. Es el piso ECONÓMICO por
    # debajo del cual rebalancear un activo es irracional (D7).
    cm = CostModel(tickers=["A0"], commission_rate=0.0043, min_fee=40.0)
    assert abs(cm.band_notional() - 40.0 / 0.0043) < 1e-6
    assert zero_cost_model(["A0"]).band_notional() == 0.0


# --------------------------------------------------------------------------
# 5b. acción relativa: "no operar" tiene que ser exacto y alcanzable (D2 enmendada)
# --------------------------------------------------------------------------
def test_delta_accion_cero_no_opera_nunca():
    """La propiedad que motiva toda la enmienda de D2.

    Con la acción absoluta, quedarse quieto exigía que la red reprodujera
    exactamente su salida anterior: un accidente. Con la acción relativa,
    a = 0 devuelve los pesos actuales AL BIT, y ese es el estado que el costo
    hace valioso.
    """
    p = panel_sintetico()
    env = PortfolioEnv(
        p,
        CostModel(tickers=p.tickers, half_spread_bps=110.0, commission_rate=0.0043, min_fee=40.0),
        EnvConfig(action_mode="delta", rebalance_every=1, band_notional=0.0),
    )
    env.reset()
    done = False
    while not done:
        res = env.step(np.zeros(env.n_slots))
        done = res[3] if len(res) == 5 else res[2]

    assert np.allclose(env.history["turnover"], 0.0), "a=0 produjo operaciones"
    assert sum(env.history["cost"]) == 0.0, "a=0 pagó costo"
    factores = 1.0 + p.rf_daily[env.t0 : env.t]
    esperado = env.cfg.initial_capital * np.concatenate([[1.0], np.cumprod(factores)])
    assert np.allclose(env.equity_curve, esperado, rtol=1e-12), (
        "sin operar, el patrimonio debería ser exactamente la caja capitalizada"
    )


def test_delta_mueve_en_la_direccion_pedida_y_acotado():
    p = panel_sintetico()
    escala = 0.05
    env = PortfolioEnv(
        p,
        zero_cost_model(p.tickers),
        EnvConfig(
            action_mode="delta", rebalance_every=1, band_notional=0.0, action_scale=escala
        ),
    )
    env.reset()
    accion = np.zeros(env.n_slots)
    accion[0] = 5.0  # tanh satura: pide el desplazamiento máximo hacia el activo 0

    previo = env.history["weights"][-1].copy()
    for _ in range(10):
        env.step(accion)
        actual = env.history["weights"][-1]
        assert actual[0] >= previo[0] - 1e-9, "el peso pedido no subió"
        assert np.max(np.abs(actual - previo)) <= 2 * escala + 1e-9, (
            "un paso movió la cartera más allá del tope por paso"
        )
        assert abs(actual.sum() - 1.0) < 1e-10
        previo = actual.copy()
    assert previo[0] > 0.3, "tras 10 pasos al máximo el activo debería estar bien cargado"


# --------------------------------------------------------------------------
# 6. el contrato de la observación (D13)
# --------------------------------------------------------------------------
def test_observacion_usa_el_dia_anterior_a_la_ejecucion():
    p = panel_sintetico()
    env = _env(p, rebalance_every=1)
    out = env.reset()
    obs = out[0] if isinstance(out, tuple) else out
    plano = p.features.flat_dim()

    assert np.allclose(obs[:plano], p.features.values[env.t0 - 1].reshape(-1)), (
        "la observación inicial no corresponde al día anterior a la primera ejecución"
    )

    w = np.zeros(env.n_slots)
    w[: env.n_assets] = 1.0 / env.n_assets
    for _ in range(5):
        res = env.step(w)
        obs = res[0]
        assert np.allclose(obs[:plano], p.features.values[env.t - 1].reshape(-1)), (
            "la observación se adelantó: rompería D13"
        )


# --------------------------------------------------------------------------
# 7. recompensas (D4)
# --------------------------------------------------------------------------
def test_dsr_premia_mejor_razon_riesgo_retorno():
    """Con el MISMO retorno, el DSR paga más cuando la volatilidad acumulada es menor.

    OJO — LO QUE NO SE PUEDE TESTEAR ASÍ, y por qué importa: la SUMA del DSR a lo
    largo de un episodio NO ordena las series por Sharpe. D_t escala como
    (R−A)/σ, así que en una serie tranquila cada término es enorme y la suma es
    un paseo aleatorio que domina a la señal (medido: −130 vs +9 para series con
    Sharpe 0.32 y 0.02). El DSR es una recompensa por paso cuya ESPERANZA guía la
    política; no es un estimador del Sharpe del episodio.
    Corolario práctico: el Sharpe que se reporta en D10 sale de la serie de
    retornos, NUNCA de la recompensa acumulada. Es otra razón para mantener
    separadas la recompensa y la evaluación.
    """
    rng = np.random.default_rng(11)
    tranquilo = DifferentialSharpe(eta=1 / 20)
    convulso = DifferentialSharpe(eta=1 / 20)
    for x in rng.normal(0.001, 0.005, 500):
        tranquilo.step(x)
    for x in rng.normal(0.001, 0.020, 500):
        convulso.step(x)

    assert tranquilo.step(0.01) > convulso.step(0.01), (
        "el DSR no premia el mismo retorno cuando la volatilidad acumulada es menor"
    )


def test_dsr_es_creciente_en_el_retorno():
    rng = np.random.default_rng(5)
    previos = rng.normal(0.001, 0.01, 400)

    def recompensa_de(r_final):
        d = DifferentialSharpe(eta=1 / 20)
        for x in previos:
            d.step(x)
        return d.step(r_final)

    valores = [recompensa_de(r) for r in (-0.03, -0.01, 0.0, 0.01, 0.03)]
    assert all(b > a for a, b in zip(valores, valores[1:])), (
        f"el DSR no es creciente en el retorno del paso: {valores}"
    )


def test_ddr_castiga_las_caidas_y_no_las_subidas():
    subidas = DifferentialDownside(eta=1 / 20)
    bajadas = DifferentialDownside(eta=1 / 20)
    base = [0.01, -0.01] * 40
    for x in base:  # calentamiento idéntico
        subidas.step(x)
        bajadas.step(x)
    r_arriba = subidas.step(0.05)
    r_abajo = bajadas.step(-0.05)
    assert r_arriba > 0 > r_abajo, "el DDR no distingue el signo del shock"


def test_recompensas_son_finitas_desde_el_primer_paso():
    for reward in (DifferentialSharpe(), DifferentialDownside()):
        vals = [reward.step(x) for x in [0.0, 0.01, -0.02, 0.005, 0.0]]
        assert all(np.isfinite(v) for v in vals), f"{reward.name} devolvió no finitos"
        assert vals[0] == 0.0, "debería haber calentamiento en el primer paso"
        assert np.all(np.isfinite(reward.state())), "el estado expuesto no es finito"


# --------------------------------------------------------------------------
# 8. integración con el panel real (se salta si no está construido)
# --------------------------------------------------------------------------
def test_panel_real_si_existe():
    from src.env.costs import snapshot_cost_model
    from src.env.panel import DEFAULT_PANEL, load_panel

    if not Path(DEFAULT_PANEL).exists():
        print("  (saltado: no existe el panel de R6)")
        return

    p = load_panel(view="solo_mercado", start="2022-01-01", end="2022-12-31", warmup=60)
    env = PortfolioEnv(
        p,
        snapshot_cost_model(p.tickers),
        EnvConfig(action_mode="weights", rebalance_every=1),
    )
    res = run_policy(env, EqualWeight())
    s = res["summary"]
    assert s["dias"] > 100, "el tramo quedó demasiado corto"
    assert np.isfinite(s["sharpe"]) and np.isfinite(s["max_drawdown"])
    assert s["costo_total"] >= 0
    print(f"  1/N 2022 neto de costos: {s}")


# --------------------------------------------------------------------------
if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(list(globals().items())):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {nombre}")
            except AssertionError as exc:
                fallos += 1
                print(f"FALLA {nombre}: {exc}")
            except Exception as exc:  # noqa: BLE001
                fallos += 1
                print(f"ERROR {nombre}: {type(exc).__name__}: {exc}")
    print("\n" + ("todos los tests pasaron" if not fallos else f"{fallos} test(s) con problemas"))
    sys.exit(1 if fallos else 0)
