"""Tests del baseline Markowitz y de las métricas de §2.2.6 (R8).

Los dos faltantes que registraba
`docs/inconsistencias_documento_vs_implementacion.txt` (entradas 7 y 8):
el baseline de media-varianza —el único de los tres del documento que no
existía— y las métricas Sortino y retorno anualizado.

QUÉ SE PRUEBA, y el orden es por importancia:

    1. CAUSALIDAD. Markowitz no puede mirar su propio día de ejecución. Es el
       mismo test de venda en los ojos que se le hizo a la sorpresa
       fundamental: se corrompe el futuro y el peso no puede moverse. Con un
       CONTROL que corrompe el pasado, porque un test de causalidad que pasa
       aunque no mire nada no prueba nada.
    2. El caso degenerado va a CAJA, no a la cartera menos mala.
    3. Los optimizadores resuelven lo que dicen resolver (contrastados contra
       perturbaciones aleatorias, no contra sí mismos).
    4. Ledoit-Wolf coincide con scikit-learn y preserva la traza.
    5. El umbral del Sortino es la TASA LIBRE DE RIESGO y no cero, y el
       retorno anualizado sigue la fórmula literal del documento.

Corre con pytest o directo:  python tests/test_markowitz.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.env.costs import zero_cost_model
from src.env.features import FeatureTensor
from src.env.panel import PanelData
from src.env.policies import (
    CashOnly,
    EqualWeight,
    Markowitz,
    _min_var_long_only,
    _tangencia_long_only,
    ledoit_wolf_cov,
    run_policy,
)
from src.env.portfolio_env import EnvConfig, PortfolioEnv
from test_portfolio_env import RF_ANUAL, panel_sintetico


def _env(panel, **cfg) -> PortfolioEnv:
    base = dict(action_mode="weights", band_notional=0.0)
    base.update(cfg)
    return PortfolioEnv(panel, zero_cost_model(panel.tickers), EnvConfig(**base))


def _primer_peso(panel: PanelData, k: int, **kw) -> np.ndarray:
    """El peso que Markowitz emite en su PRIMER paso, arrancando en el índice k."""
    env = _env(panel, start_index=k, rebalance_every=1)
    pol = Markowitz(window=60, min_obs=20, **kw)
    pol.reset()
    out = env.reset()
    obs = out[0] if isinstance(out, tuple) else out
    return pol.act(obs, env)


# --------------------------------------------------------------------------
# 1. causalidad — el test que más importa
# --------------------------------------------------------------------------
def test_markowitz_no_mira_su_dia_de_ejecucion():
    k = 120
    rng = np.random.default_rng(99)

    base = panel_sintetico(n_dias=200, n_activos=4, seed=3)
    futuro_roto = panel_sintetico(n_dias=200, n_activos=4, seed=3)
    futuro_roto.prices[k:] *= 1.0 + rng.normal(0.0, 0.08, size=futuro_roto.prices[k:].shape)

    w_base = _primer_peso(base, k)
    w_roto = _primer_peso(futuro_roto, k)
    assert np.allclose(w_base, w_roto, atol=1e-12), (
        "cambiar los precios DESDE el día de ejecución movió la decisión: "
        "la ventana de estimación está mirando hacia adelante"
    )

    # CONTROL: si corromper el PASADO tampoco moviera el peso, el test de
    # arriba pasaría por no estar mirando nada y no probaría causalidad.
    pasado_roto = panel_sintetico(n_dias=200, n_activos=4, seed=3)
    pasado_roto.prices[k - 40 : k] *= 1.0 + rng.normal(
        0.0, 0.08, size=pasado_roto.prices[k - 40 : k].shape
    )
    w_pasado = _primer_peso(pasado_roto, k)
    assert not np.allclose(w_base, w_pasado, atol=1e-6), (
        "corromper la ventana de estimación no movió el peso: el control falló "
        "y el test de causalidad no está probando nada"
    )


# --------------------------------------------------------------------------
# 2. el caso degenerado va a caja
# --------------------------------------------------------------------------
def test_sin_activo_sobre_la_tasa_libre_de_riesgo_se_va_a_caja():
    # universo que solo cae: ningún retorno esperado supera a la caja.
    n_dias, n_act = 200, 3
    p = panel_sintetico(n_dias=n_dias, n_activos=n_act, seed=11)
    p.prices[:] = 100.0 * np.cumprod(
        np.full((n_dias, n_act), 1.0 - 0.001), axis=0
    )

    env = _env(p, start_index=120, rebalance_every=1)
    pol = Markowitz(window=60, min_obs=20)
    res = run_policy(env, pol)

    assert pol.n_degenerado == pol.n_resueltos > 0, (
        f"el problema debería salir degenerado siempre: "
        f"{pol.n_degenerado} de {pol.n_resueltos}"
    )
    pesos = res["weights"]
    assert np.allclose(pesos[1:, -1], 1.0), "no se fue 100% a caja en el caso degenerado"

    # y si está en caja, tiene que rendir EXACTAMENTE lo que rinde la caja.
    env_caja = _env(p, start_index=120, rebalance_every=1)
    res_caja = run_policy(env_caja, CashOnly())
    assert np.allclose(res["equity"], res_caja["equity"], rtol=1e-12), (
        "la cartera degenerada no replica a CashOnly"
    )


# --------------------------------------------------------------------------
# 3. los optimizadores resuelven lo que dicen
# --------------------------------------------------------------------------
def _cov_ejemplo(seed: int = 5, n: int = 5) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0005, 0.011, size=(300, n))
    rets[:, 0] += 0.0008  # un activo claramente bueno
    return rets.mean(axis=0), np.cov(rets, rowvar=False, ddof=1)


def test_min_var_es_de_verdad_la_de_varianza_minima():
    _, cov = _cov_ejemplo()
    w = _min_var_long_only(cov)
    assert np.all(w >= -1e-9) and np.isclose(w.sum(), 1.0), "no es una cartera del símplex"

    var_opt = float(w @ cov @ w)
    rng = np.random.default_rng(0)
    rivales = rng.dirichlet(np.ones(len(w)), size=2000)
    peor = (rivales @ cov * rivales).sum(axis=1).min()
    assert var_opt <= peor + 1e-12, (
        f"2,000 carteras aleatorias encontraron menos varianza ({peor:.3e}) "
        f"que el optimizador ({var_opt:.3e})"
    )


def test_tangencia_maximiza_el_sharpe_sobre_el_simplex():
    mu, cov = _cov_ejemplo()
    rf = 0.0002
    w = _tangencia_long_only(mu - rf, cov)
    assert w is not None and np.isclose(w.sum(), 1.0) and np.all(w >= -1e-9)

    def sharpe(x):
        vol = np.sqrt(x @ cov @ x)
        return (x @ (mu - rf)) / vol if vol > 0 else -np.inf

    rng = np.random.default_rng(1)
    rivales = rng.dirichlet(np.ones(len(w)), size=2000)
    mejor_rival = max(sharpe(x) for x in rivales)
    assert sharpe(w) >= mejor_rival - 1e-9, (
        f"2,000 carteras aleatorias batieron a la tangente "
        f"({mejor_rival:.4f} vs {sharpe(w):.4f})"
    )
    assert sharpe(w) >= sharpe(np.full(len(w), 1.0 / len(w))) - 1e-12, (
        "la tangente no le gana al 1/N en la MISMA muestra con que se estimó"
    )


# --------------------------------------------------------------------------
# 4. Ledoit-Wolf
# --------------------------------------------------------------------------
def test_ledoit_wolf_preserva_la_traza_y_mejora_el_condicionamiento():
    rng = np.random.default_rng(4)
    # más activos que observaciones holgadas: es donde el encogimiento importa
    rets = rng.normal(0.0, 0.01, size=(30, 8))
    s = (lambda x: (x - x.mean(0)).T @ (x - x.mean(0)) / len(x))(rets)
    lw = ledoit_wolf_cov(rets)

    assert np.isclose(np.trace(lw), np.trace(s), rtol=1e-12), (
        "el encogimiento hacia identidad escalada debe preservar la traza"
    )
    assert np.linalg.cond(lw) <= np.linalg.cond(s) + 1e-9, (
        "la matriz encogida quedó peor condicionada que la muestral"
    )
    assert np.allclose(lw, lw.T), "la covarianza encogida no es simétrica"
    assert np.all(np.linalg.eigvalsh(lw) > 0), "la covarianza encogida no es definida positiva"


def test_ledoit_wolf_coincide_con_sklearn_si_esta_instalado():
    try:
        from sklearn.covariance import ledoit_wolf
    except ImportError:
        print("  (saltado: scikit-learn no está instalado)")
        return
    rng = np.random.default_rng(8)
    rets = rng.normal(0.0, 0.01, size=(40, 6))
    esperado, _ = ledoit_wolf(rets)
    assert np.allclose(ledoit_wolf_cov(rets), esperado, rtol=1e-10, atol=1e-14), (
        "la implementación propia de Ledoit-Wolf no coincide con scikit-learn"
    )


# --------------------------------------------------------------------------
# 5. integración: pesos válidos y las dos variantes corren sobre el simulador
# --------------------------------------------------------------------------
def test_markowitz_produce_carteras_validas_en_todo_paso():
    p = panel_sintetico(n_dias=250, n_activos=5, seed=21)
    for kw in ({}, {"shrinkage": "ledoit_wolf"}, {"objetivo": "min_var"}):
        env = _env(p, start_index=120, rebalance_every=5)
        res = run_policy(env, Markowitz(window=60, min_obs=20, **kw))
        w = res["weights"]
        assert np.all(w >= -1e-9), f"pesos negativos con {kw}"
        assert np.allclose(w.sum(axis=1), 1.0, atol=1e-9), f"los pesos no suman 1 con {kw}"
        assert np.all(np.isfinite(res["equity"])), f"patrimonio no finito con {kw}"


def test_markowitz_respeta_la_frecuencia_de_rebalanceo_del_entorno():
    """Requisito de equidad de D10: la frecuencia la fija el ENTORNO."""
    p = panel_sintetico(n_dias=250, n_activos=5, seed=22)
    env = _env(p, start_index=120, rebalance_every=21)
    pol = Markowitz(window=60, min_obs=20)
    run_policy(env, pol)
    pasos = env.step_count
    esperado = int(np.ceil(pasos / 21))
    assert pol.n_resueltos == esperado, (
        f"re-optimizó {pol.n_resueltos} veces en {pasos} pasos con rebalanceo cada 21; "
        f"esperado {esperado}. Estimar más seguido que lo que se opera no cambia la "
        "cartera pero sí el costo computacional, y desalinea estimación y acción."
    )


# --------------------------------------------------------------------------
# 6. métricas de §2.2.6
# --------------------------------------------------------------------------
def test_retorno_anualizado_usa_la_formula_del_documento():
    p = panel_sintetico(n_dias=300, n_activos=4, seed=31)
    env = _env(p, rebalance_every=1)
    s = run_policy(env, EqualWeight())["summary"]
    esperado = (1.0 + s["retorno_total"]) ** (252.0 / s["dias"]) - 1.0
    assert np.isclose(s["retorno_anualizado"], esperado, rtol=1e-12), (
        "R_anual no sigue (V_final/V_inicial)^(252/n) - 1"
    )


def test_caja_anualiza_exactamente_la_tasa_libre_de_riesgo():
    p = panel_sintetico(n_dias=300, n_activos=3, seed=32)
    env = _env(p, rebalance_every=1)
    s = run_policy(env, CashOnly())["summary"]
    esperado = (1.0 + RF_ANUAL / 365.0) ** 252.0 - 1.0
    assert np.isclose(s["retorno_anualizado"], esperado, rtol=1e-10), (
        f"la caja anualizó {s['retorno_anualizado']:.6f} en vez de {esperado:.6f}"
    )
    # Convención declarada: sin retornos por debajo del umbral, el Sortino no
    # está definido y se devuelve 0.0, igual que el Sharpe con volatilidad cero.
    assert s["sortino"] == 0.0 and s["sharpe"] == 0.0
    assert s["downside_dev_anual"] == 0.0


def test_caja_con_tasa_VARIABLE_no_inventa_un_sortino():
    """El caso que rompió la primera versión de la métrica.

    Con tasa constante el test anterior pasa por casualidad. Con la tasa
    MOVIÉNDOSE —que es el panel real, donde el BCRP va de 0.25% a 7.75%— el
    retorno del paso sale de dividir dos patrimonios de ~1e6 y no coincide
    BIT A BIT con la tasa del día. Sin piso de ruido, el Sortino de la caja
    es un 0/0 disfrazado: sobre el panel real devolvía −14.99.
    """
    p = panel_sintetico(n_dias=400, n_activos=3, seed=34)
    rng = np.random.default_rng(7)
    p.rf_daily = rng.choice([0.0025, 0.0175, 0.0425, 0.0775], size=p.n_steps) / 365.0

    s = run_policy(_env(p, rebalance_every=1), CashOnly())["summary"]
    assert s["downside_dev_anual"] == 0.0, (
        f"la caja nunca cae por debajo de la tasa libre de riesgo, pero se midió "
        f"una desviación a la baja de {s['downside_dev_anual']:.3e}"
    )
    assert s["sortino"] == 0.0, f"Sortino inventado para la caja: {s['sortino']:.4f}"
    assert s["sharpe"] == 0.0, f"Sharpe inventado para la caja: {s['sharpe']:.4f}"
    # y la caja sigue rindiendo de verdad: el ruido se anuló, no el retorno.
    assert s["retorno_total"] > 0.0


def test_el_umbral_del_sortino_es_la_tasa_libre_de_riesgo_no_cero():
    """Si el umbral fuera cero, subir la tasa del BCRP no cambiaría el Sortino."""
    barata = panel_sintetico(n_dias=300, n_activos=4, seed=33)
    cara = panel_sintetico(n_dias=300, n_activos=4, seed=33)
    cara.rf_daily = np.full_like(cara.rf_daily, 0.08 / 365.0)  # 0.25% -> 8% anual

    s_b = run_policy(_env(barata, rebalance_every=1), EqualWeight())["summary"]
    s_c = run_policy(_env(cara, rebalance_every=1), EqualWeight())["summary"]

    assert s_c["downside_dev_anual"] > s_b["downside_dev_anual"], (
        "subir la tasa libre de riesgo no aumentó la desviación a la baja: "
        "el umbral del Sortino no es la tasa, es cero"
    )
    assert s_c["sortino"] < s_b["sortino"], "el Sortino no cayó al subir el umbral"


def test_sortino_contra_sharpe_segun_la_asimetria():
    """Con pérdidas chicas y frecuentes vs. ganancias grandes y raras, la
    desviación a la baja es MENOR que la volatilidad total, así que el Sortino
    tiene que quedar POR ENCIMA del Sharpe. Y al revés con el signo invertido."""

    def panel_con_retornos(r: np.ndarray) -> PanelData:
        n = len(r) + 1
        precios = (100.0 * np.cumprod(np.concatenate([[1.0], 1.0 + r])))[:, None]
        return PanelData(
            dates=np.array([np.datetime64("2020-01-01") + np.timedelta64(i, "D") for i in range(n)]),
            tickers=["A0"],
            prices=precios,
            no_trade=np.zeros((n, 1), dtype=bool),
            stale=np.zeros((n, 1), dtype=bool),
            rf_daily=np.zeros(n),
            features=FeatureTensor(
                values=np.zeros((n, 1, 2), dtype=np.float32),
                columns=["f0", "f1"],
                tickers=["A0"],
                warmup=0,
            ),
        )

    base = np.where(np.arange(240) % 12 == 0, 0.05, -0.003)  # sesgo a la derecha
    derecha = run_policy(
        _env(panel_con_retornos(base), rebalance_every=10**9), EqualWeight()
    )["summary"]
    izquierda = run_policy(
        _env(panel_con_retornos(-base), rebalance_every=10**9), EqualWeight()
    )["summary"]

    assert derecha["sortino"] > derecha["sharpe"] > 0, (
        f"con sesgo a la derecha el Sortino ({derecha['sortino']:.3f}) debería superar "
        f"al Sharpe ({derecha['sharpe']:.3f})"
    )
    assert izquierda["sortino"] < izquierda["sharpe"] < 0, (
        f"con sesgo a la izquierda el Sortino ({izquierda['sortino']:.3f}) debería quedar "
        f"por debajo del Sharpe ({izquierda['sharpe']:.3f})"
    )


# --------------------------------------------------------------------------
# 7. panel real (se salta si no está construido)
# --------------------------------------------------------------------------
def test_markowitz_sobre_el_panel_real_si_existe():
    from src.env.costs import snapshot_cost_model
    from src.env.panel import DEFAULT_PANEL, load_panel

    if not Path(DEFAULT_PANEL).exists():
        print("  (saltado: no existe el panel de R6)")
        return

    p = load_panel(view="solo_mercado", start="2018-01-01", end="2019-12-31", warmup=60)
    env = PortfolioEnv(
        p,
        snapshot_cost_model(p.tickers),
        EnvConfig(action_mode="weights", rebalance_every=21),
    )
    pol = Markowitz(window=252, min_obs=60)
    res = run_policy(env, pol)
    s = res["summary"]
    assert s["dias"] > 200 and np.isfinite(s["sharpe"]) and np.isfinite(s["sortino"])
    assert np.allclose(np.asarray(res["weights"]).sum(axis=1), 1.0, atol=1e-9)
    print(
        f"  markowitz 2018-2019: ret {s['retorno_total']:+.2%} "
        f"anual {s['retorno_anualizado']:+.2%} sharpe {s['sharpe']:.2f} "
        f"sortino {s['sortino']:.2f} rot {s['rotacion_anual']:.2f} | "
        f"degenerado {pol.n_degenerado}/{pol.n_resueltos}"
    )


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
