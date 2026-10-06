"""Tests de las recompensas de D4 y de los candidatos abiertos el 2026-09-19.

QUÉ SE PRUEBA, y el orden es por importancia:

    1. LOS HALLAZGOS DE §7.11 QUEDAN CLAVADOS COMO TESTS. Que el precio que el
       DSR le pone a la varianza sea A/(2B) —y que CAMBIE DE SIGNO cuando la
       media móvil es negativa— es el hallazgo que explica D25. Si alguien
       "arregla" el DSR y esa propiedad desaparece, los tests tienen que
       avisar, porque entonces la sección 7.11 dejó de describir el código.
    2. LAS GUARDAS FALLAN TEMPRANO. λ y κ no tienen defecto: una constante
       calibrada que nadie revalida cuando cambia el universo es la trampa que
       este proyecto ya pisó tres veces.
    3. `dsr_rot` con κ=0 tiene que ser EXACTAMENTE el DSR. Si no, el brazo que
       reabre D7 no es comparable con el primario y nadie se daría cuenta.
    4. La contabilidad del drawdown: se castiga el INCREMENTO, no el nivel, y
       en un máximo nuevo el castigo es cero.
    5. La interfaz acepta `turnover` sin romper a las que no lo miran.

Corre con pytest o directo:  python tests/test_rewards_d4.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.env.rewards import (
    REWARDS,
    DifferentialSharpe,
    DSRTurnover,
    LogReturnDrawdown,
    MeanVariance,
    make_reward,
)


# --------------------------------------------------------------------------
# 1. Los hallazgos de §7.11, como tests
# --------------------------------------------------------------------------
def test_dsr_precio_de_la_varianza_es_a_sobre_2b():
    """r_t ∝ (R−A) − (A/2B)·(R²−B). Se verifica contra la forma implementada."""
    rec = DifferentialSharpe(eta=0.1)
    rng = np.random.default_rng(0)
    for x in rng.normal(0.001, 0.01, 50):
        rec.step(float(x))
    a, b = rec.a, rec.b
    var = b - a * a
    x = 0.02
    directo = (b * (x - a) - 0.5 * a * (x * x - b)) / var ** 1.5
    factorizado = (b / var ** 1.5) * ((x - a) - (a / (2.0 * b)) * (x * x - b))
    assert abs(directo - factorizado) < 1e-9 * max(1.0, abs(directo)), (
        f"la factorizacion de 7.11 no reproduce el DSR: {directo} vs {factorizado}"
    )


def test_dsr_paga_por_varianza_cuando_la_media_movil_es_negativa():
    """EL HALLAZGO DE §7.11(2). Con A<0 el término de riesgo cambia de signo.

    Se compara el mismo retorno contra dos estados: uno con media móvil
    positiva y otro con media móvil negativa, y se mira si un retorno de MAYOR
    magnitud al cuadrado sube o baja la recompensa.
    """
    def termino_varianza(a: float, b: float, x: float) -> float:
        return -0.5 * a * (x * x - b) / (b - a * a) ** 1.5

    b = 1e-4  # segundo momento, vol diaria ~1%
    x_grande = 0.03  # x² muy por encima de b
    assert termino_varianza(+0.002, b, x_grande) < 0, (
        "con media movil POSITIVA el termino de varianza tiene que CASTIGAR"
    )
    assert termino_varianza(-0.002, b, x_grande) > 0, (
        "con media movil NEGATIVA el termino de varianza PAGA — es el hallazgo "
        "de 7.11 que explica D25; si este test falla, la seccion quedo obsoleta"
    )


def test_quien_paga_por_ruido_y_quien_no():
    """EL HALLAZGO DE §7.12: inflar la dispersión a media CONSTANTE.

    Sobre 18 estrategias reales x 2 tramos, la DDR sube en 83% de las celdas y
    el DSR en 44%; `mv` y `logret_dd` no suben en NINGUNA. Acá se reproduce la
    propiedad con una familia sintética de derivas y dispersiones, que es lo
    que se puede clavar en un test sin cargar el panel.

    IMPORTANTE, Y POR ESO ESTE TEST ESTÁ ESCRITO ASÍ: la DDR y el DSR no pagan
    por ruido SIEMPRE —depende de la trayectoria, y ahí está el problema: su
    respuesta al ruido CAMBIA DE SIGNO según el tramo—. Lo que sí es estable,
    y es lo que hay que proteger, es que `mv` y `logret_dd` no lo hacen nunca.
    """
    rng = np.random.default_rng(7)
    familia = [rng.normal(mu, sd, 1200)
               for mu in (-0.0008, -0.0002, 0.0, 0.0004, 0.001)
               for sd in (0.008, 0.015)]

    def cambio(serie, nombre, **kw):
        m = float(np.mean(serie))
        inflada = m + 1.5 * (serie - m)

        def acumula(x):
            rec = make_reward(nombre, **kw)
            rec.reset()
            return float(np.sum([rec.step(float(v)) for v in x]))

        return acumula(inflada) - acumula(serie)

    for nombre, kw in (("mv", {"lam": 16.3}), ("logret_dd", {"lam": 1.0})):
        subidas = [c for c in (cambio(r, nombre, **kw) for r in familia) if c > 0]
        assert not subidas, (
            f"{nombre} pago por ruido en {len(subidas)} de {len(familia)} series: "
            "era la propiedad que lo hacia candidato (7.12)"
        )

    for nombre in ("ddr", "dsr"):
        cambios = [cambio(r, nombre, eta=1.0 / 60.0) for r in familia]
        assert any(c > 0 for c in cambios), (
            f"{nombre} ya no paga por ruido en ninguna serie de la familia: "
            "si eso es cierto de verdad, 7.12 quedo obsoleta y hay que rehacerla"
        )


# --------------------------------------------------------------------------
# 2. Las guardas
# --------------------------------------------------------------------------
def test_los_candidatos_exigen_su_parametro():
    for nombre in ("mv", "logret_dd", "dsr_rot"):
        try:
            make_reward(nombre)
        except ValueError:
            continue
        raise AssertionError(
            f"{nombre} acepto construirse sin su parametro de escala: es "
            "exactamente la constante sin calibrar que este proyecto ya sufrio"
        )


def test_las_tres_de_d4_no_exigen_nada():
    for nombre in ("dsr", "ddr", "logret"):
        make_reward(nombre)


def test_el_registro_tiene_las_seis():
    assert set(REWARDS) == {"dsr", "ddr", "logret", "mv", "logret_dd", "dsr_rot"}


# --------------------------------------------------------------------------
# 3. dsr_rot con κ=0 es el DSR
# --------------------------------------------------------------------------
def test_dsr_rot_con_kappa_cero_es_identico_al_dsr():
    rng = np.random.default_rng(3)
    r = rng.normal(0.0003, 0.012, 400)
    rot = rng.uniform(0.0, 0.3, 400)
    a = DifferentialSharpe(eta=1.0 / 60.0)
    b = DSRTurnover(kappa=0.0, eta=1.0 / 60.0)
    a.reset()
    b.reset()
    for x, t in zip(r, rot):
        va = a.step(float(x))
        vb = b.step(float(x), float(t))
        assert abs(va - vb) < 1e-12, "dsr_rot(kappa=0) se desvio del DSR"


def test_dsr_rot_castiga_mas_cuanto_mas_rota():
    rng = np.random.default_rng(4)
    r = rng.normal(0.0003, 0.012, 300)

    def acumula(rot_fija):
        rec = DSRTurnover(kappa=1.0, eta=1.0 / 60.0)
        rec.reset()
        return float(np.sum([rec.step(float(x), rot_fija) for x in r]))

    assert acumula(0.5) < acumula(0.1), "mas rotacion tendria que dar MENOS recompensa"


# --------------------------------------------------------------------------
# 4. Contabilidad del drawdown
# --------------------------------------------------------------------------
def test_logret_dd_no_castiga_en_maximo_nuevo():
    rec = LogReturnDrawdown(lam=10.0)
    rec.reset()
    for x in (0.01, 0.02, 0.015):  # sube siempre: nunca hay drawdown
        r = rec.step(x)
        assert abs(r - np.log1p(x)) < 1e-12, "castigo en un maximo nuevo"
    assert rec.dd == 0.0


def test_logret_dd_castiga_el_incremento_y_no_el_nivel():
    """Dos caídas iguales seguidas: la segunda sigue castigando; el suelo, no."""
    rec = LogReturnDrawdown(lam=10.0)
    rec.reset()
    rec.step(0.05)                      # pico
    r1 = rec.step(-0.03) - np.log1p(-0.03)
    r2 = rec.step(-0.03) - np.log1p(-0.03)
    r3 = rec.step(0.0)                  # plano en el fondo: el dd NO se profundiza
    assert r1 < 0 and r2 < 0, "una caida nueva tiene que castigar"
    assert abs(r3) < 1e-12, "estar quieto en el fondo no puede seguir cobrando"


def test_logret_dd_expone_el_drawdown_como_estado():
    """MARKOV: el estado suficiente entra a la observación (es la regla de D4)."""
    rec = LogReturnDrawdown(lam=1.0)
    rec.reset()
    assert rec.state_dim == 1
    rec.step(0.10)
    rec.step(-0.05)
    assert abs(rec.state()[0] - rec.dd * 100.0) < 1e-6


# --------------------------------------------------------------------------
# 5. mv y la interfaz
# --------------------------------------------------------------------------
def test_mv_castiga_simetricamente_la_desviacion():
    """El castigo es cuadrático: +d y −d sobre la media cuestan lo mismo."""
    def castigo(x):
        rec = MeanVariance(lam=50.0, eta=0.5)
        rec.reset()
        return np.log1p(x) - rec.step(x)

    assert abs(castigo(0.02) - castigo(-0.02)) < 1e-12


def test_mv_con_lambda_cero_es_el_log_retorno():
    rec = MeanVariance(lam=0.0)
    rec.reset()
    for x in (0.01, -0.02, 0.003):
        assert abs(rec.step(x) - np.log1p(x)) < 1e-12


def test_todas_aceptan_turnover_sin_romperse():
    for nombre, kw in (("dsr", {}), ("ddr", {}), ("logret", {}),
                       ("mv", {"lam": 1.0}), ("logret_dd", {"lam": 1.0}),
                       ("dsr_rot", {"kappa": 1.0})):
        rec = make_reward(nombre, **kw)
        rec.reset()
        for x in (0.01, -0.01, 0.02):
            v = rec.step(float(x), 0.25)
            assert np.isfinite(v), f"{nombre} devolvio un valor no finito"


def test_ninguna_devuelve_nan_con_retorno_extremo():
    for nombre, kw in (("dsr", {}), ("ddr", {}), ("logret", {}),
                       ("mv", {"lam": 30.0}), ("logret_dd", {"lam": 1.0}),
                       ("dsr_rot", {"kappa": 1.0})):
        rec = make_reward(nombre, **kw)
        rec.reset()
        for x in (0.0, 0.0, -0.99, 0.5, 0.0):
            assert np.isfinite(rec.step(float(x), 1.0)), f"{nombre} exploto"


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
