"""Tests de la forma de la señal fundamental (acta §B3).

LO QUE IMPORTA ACÁ ES LA CAUSALIDAD. Una sorpresa que use el trimestre siguiente
infla el backtest y lo invalida, y no hace fallar nada: sale un número precioso.
Por eso el test central es el de la venda en los ojos —recalcular con el futuro
borrado y exigir el MISMO resultado—, que es la única forma de probar que no se
está mirando adelante.

    python tests/test_fundamental_shape.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.env.fundamental_shape import (
    MIN_HISTORIA, agrega_forma_fundamental, dist_media_movil, sue_serie,
)


# --------------------------------------------------------------------------
# sue_serie
# --------------------------------------------------------------------------
def test_serie_perfectamente_predecible_no_sorprende():
    """Si la serie crece siempre igual, la deriva la explica y la sorpresa es ~0."""
    x = np.arange(30, dtype=float)          # +1 por trimestre, sin ruido
    s = sue_serie(x, lag=1)
    # Los primeros quedan en 0 por falta de historia; el resto debe ser ~0
    # porque sigma->0 y el módulo devuelve 0 en vez de dividir por casi nada.
    assert np.all(np.abs(s) < 1e-6), f"máximo {np.abs(s).max()}"


def test_un_salto_grande_produce_sorpresa_grande_y_con_signo():
    rng = np.random.default_rng(0)
    x = 100 + np.cumsum(rng.normal(0, 1, 40))
    x[30] += 25.0                            # sorpresa positiva fuerte
    s = sue_serie(x, lag=1)
    assert s[30] > 3.0, f"sorpresa de {s[30]:.2f}, se esperaba grande y positiva"
    assert abs(s[29]) < abs(s[30])

    y = x.copy()
    y[30] -= 50.0                            # ahora al revés
    s2 = sue_serie(y, lag=1)
    assert s2[30] < -3.0, f"sorpresa de {s2[30]:.2f}, se esperaba grande y negativa"


def test_no_emite_sin_historia_suficiente():
    x = np.arange(20, dtype=float) + np.random.default_rng(1).normal(0, 1, 20)
    s = sue_serie(x, lag=4, min_historia=MIN_HISTORIA)
    # Con lag=4 y min_historia=4 hacen falta 4 diferencias previas, o sea que
    # los primeros 4+4 trimestres no pueden emitir.
    assert np.all(s[: 4 + MIN_HISTORIA] == 0.0)


def test_CAUSAL_no_mira_el_futuro():
    """La venda en los ojos: borrar el futuro no puede cambiar el pasado.

    Se calcula la serie completa y después se recalcula truncando en q. Si el
    valor en q cambia, es porque se estaba usando información posterior.
    """
    rng = np.random.default_rng(7)
    x = 50 + np.cumsum(rng.normal(0, 2, 45))
    completa = sue_serie(x, lag=4)
    for q in (12, 20, 33, 44):
        truncada = sue_serie(x[: q + 1], lag=4)
        assert np.isclose(completa[q], truncada[q], atol=1e-12), (
            f"q={q}: con futuro {completa[q]:.6f} vs sin futuro {truncada[q]:.6f}"
        )


def test_serie_corta_no_revienta():
    assert sue_serie(np.array([1.0]), lag=4).shape == (1,)
    assert np.all(sue_serie(np.array([1.0, 2.0]), lag=4) == 0.0)


# --------------------------------------------------------------------------
# dist_media_movil
# --------------------------------------------------------------------------
def test_media_movil_excluye_el_trimestre_actual():
    # media de los 4 anteriores = 10; el actual es 15 -> +50%
    x = np.array([10.0, 10.0, 10.0, 10.0, 15.0])
    d = dist_media_movil(x, ventana=4)
    assert np.isclose(d[4], 0.5), d[4]
    assert np.all(d[:4] == 0.0), "sin 4 previos no debería emitir"


def test_media_movil_con_media_cero_no_explota():
    x = np.array([-1.0, 1.0, -1.0, 1.0, 5.0])   # media de los 4 previos = 0
    d = dist_media_movil(x, ventana=4)
    assert np.all(np.isfinite(d))
    assert d[4] == 0.0


# --------------------------------------------------------------------------
# integración con el panel largo
# --------------------------------------------------------------------------
def _panel_sintetico() -> pd.DataFrame:
    """Dos activos, 16 trimestres, arrastrados a días como hace R6.

    La serie lleva RUIDO a propósito. Una serie perfectamente determinista tiene
    sigma cero en sus diferencias y entonces no hay escala contra la cual medir
    una sorpresa — ver `test_sigma_cero_no_emite_sorpresa`. Los fundamentales
    reales nunca son deterministas, así que el ruido es el caso realista.
    """
    rng = np.random.default_rng(11)
    filas = []
    for ticker, base in [("A", 1.0), ("B", 3.0)]:
        ruido = rng.normal(0, 0.05, 16)
        for i in range(16):
            period = pd.Timestamp("2013-03-31") + pd.offsets.QuarterEnd(i)
            known = period + pd.Timedelta(days=40)
            valor = base + 0.1 * i + ruido[i] + (2.0 if i == 12 else 0.0)  # salto en el 12
            for d in range(5):                                   # 5 días por trimestre
                filas.append({
                    "ticker": ticker,
                    "date": known + pd.Timedelta(days=d),
                    "period": period,
                    "known_date": known,
                    "eps_ttm": valor,
                    "roe": valor / 20.0,
                    "net_margin": valor / 30.0,
                })
    return pd.DataFrame(filas)


def test_sigma_cero_no_emite_sorpresa():
    """Caso degenerado, DECIDIDO y no accidental.

    Si la historia de diferencias no tiene dispersión (serie perfectamente
    predecible), no existe escala contra la cual estandarizar y el módulo emite
    0 en vez de dividir por casi-cero y devolver un valor enorme y arbitrario.
    La contrapartida —un salto contra una historia perfectamente plana no se
    reporta como sorpresa en SU trimestre— se acepta porque no ocurre en datos
    reales y la alternativa (un infinito) es peor.
    """
    x = np.concatenate([np.arange(10, dtype=float), [50.0]])   # +1 exacto, luego salto
    s = sue_serie(x, lag=1)
    assert s[10] == 0.0, f"con sigma=0 debería emitir 0, emitió {s[10]}"
    assert np.all(np.isfinite(s))


def test_agrega_columnas_esperadas():
    out = agrega_forma_fundamental(_panel_sintetico())
    for c in ("sue_eps_ttm", "fund_dist_ma4_roe", "pico_sue_eps_ttm",
              "dias_desde_resultado", "sue_valido"):
        assert c in out.columns, f"falta {c}"
    assert np.all(np.isfinite(out["sue_eps_ttm"]))


def test_el_pico_se_dispara_una_sola_vez_por_trimestre():
    out = agrega_forma_fundamental(_panel_sintetico())
    veces = out[out["pico_sue_eps_ttm"] != 0.0].groupby(["ticker", "period"]).size()
    assert (veces == 1).all(), f"el pico se disparó más de una vez: {veces[veces > 1]}"
    assert len(veces) > 5, "el pico casi nunca se activa"


def test_el_pico_se_dispara_aunque_la_publicacion_caiga_en_no_bursatil():
    """El defecto que tuvo la primera versión: 23% de los `known_date` reales
    caen en sábado, domingo o feriado. Exigir coincidencia EXACTA perdía uno de
    cada cuatro anuncios, y no al azar sino según el calendario."""
    p = _panel_sintetico()
    # Se aleja la publicación 2 días de la primera fila observable: simula el
    # anuncio en día no bursátil, con el mercado reaccionando después.
    p = p.copy()
    p["known_date"] = pd.to_datetime(p["known_date"]) - pd.Timedelta(days=2)
    out = agrega_forma_fundamental(p)
    coincide_exacto = (
        pd.to_datetime(out["date"]).dt.normalize()
        == pd.to_datetime(out["known_date"]).dt.normalize()
    )
    assert not coincide_exacto.any(), "el fixture debía no tener coincidencias exactas"
    assert (out["pico_sue_eps_ttm"] != 0.0).any(), (
        "sin coincidencia exacta el pico no se disparó: volvió el defecto"
    )


def test_el_pico_cae_en_la_primera_fila_del_trimestre():
    out = agrega_forma_fundamental(_panel_sintetico()).sort_values(
        ["ticker", "period", "date"]
    )
    for (_, _), g in out.groupby(["ticker", "period"]):
        activos = np.flatnonzero(g["pico_sue_eps_ttm"].to_numpy() != 0.0)
        if activos.size:
            assert activos.tolist() == [0], "el pico no cayó en el primer día del trimestre"


def test_el_escalon_se_mantiene_dentro_del_trimestre():
    """`sue_` es escalón (constante dentro del trimestre); `pico_` no."""
    out = agrega_forma_fundamental(_panel_sintetico())
    g = out[out.ticker == "A"].groupby("period")["sue_eps_ttm"].nunique()
    assert (g == 1).all(), "la sorpresa cambió dentro de un mismo trimestre"


def test_el_salto_sintetico_aparece_como_sorpresa():
    out = agrega_forma_fundamental(_panel_sintetico())
    a = out[out.ticker == "A"].drop_duplicates("period").sort_values("period")
    s = a["sue_eps_ttm"].to_numpy()
    assert s[12] == s.max() and s[12] > 3.0, f"el salto no destacó: {np.round(s, 2)}"


def test_panel_sin_period_se_devuelve_intacto():
    df = pd.DataFrame({"ticker": ["A"], "date": [pd.Timestamp("2020-01-01")], "roe": [0.1]})
    assert agrega_forma_fundamental(df).equals(df)


def test_no_pisa_columnas_existentes():
    p = _panel_sintetico()
    out = agrega_forma_fundamental(p)
    for c in p.columns:
        assert c in out.columns
        assert out[c].tolist() == p[c].tolist(), f"se modificó {c}"


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
