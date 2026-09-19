"""Test del desfase de UN DÍA del endpoint share-values de la BVL.

EL DEFECTO (2026-09-12): el endpoint etiqueta cada cierre con el SIGUIENTE día
de negociación. Sobrevivió a R3-R6 completos y a varias validaciones porque
nunca se contrastó contra una fuente externa con fechas confiables. Es el caso
más grave del patrón registrado en `feedback_deriva_decidido_implementado`.

El test usa datos REALES —la segunda vuelta de 2021, Alicorp— y no un caso
sintético, porque el valor probatorio está justamente en que las dos fuentes
independientes coincidan tras corregir.

    python tests/test_desfase_fecha_bvl.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.market.market_client import corrige_etiqueta_bvl

# Respuesta LITERAL de GET /v1/stock-quote/share-values/ALICORC1
# ?startDate=2021-06-01&endDate=2021-06-11  (consultada el 2026-09-12).
CRUDO_BVL = [
    ("2021-06-02", 6.35), ("2021-06-03", 6.41), ("2021-06-04", 6.50),
    ("2021-06-07", 6.82), ("2021-06-08", 5.79), ("2021-06-09", 5.88),
    ("2021-06-10", 6.05), ("2021-06-11", 6.50),
]

# PX_LAST de Bloomberg para el mismo activo y rango (grid_ul1wocu2.xlsx, hoja
# BASE). Es la referencia con fechas confiables.
BLOOMBERG = {
    "2021-06-02": 6.41, "2021-06-03": 6.50, "2021-06-04": 6.82,
    "2021-06-07": 5.79, "2021-06-08": 5.88, "2021-06-09": 6.05,
    "2021-06-10": 6.50,
}


def _df_crudo() -> pd.DataFrame:
    df = pd.DataFrame(CRUDO_BVL, columns=["date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_corregido_coincide_con_bloomberg():
    """Tras corregir, el cierre de cada fecha es el de Bloomberg. Exacto."""
    out = corrige_etiqueta_bvl(_df_crudo()).set_index("date")["close"]
    for fecha, esperado in BLOOMBERG.items():
        obtenido = out.loc[pd.Timestamp(fecha)]
        assert abs(obtenido - esperado) < 1e-9, (
            f"{fecha}: corregido {obtenido} != Bloomberg {esperado}"
        )


def test_sin_corregir_NO_coincide():
    """La guarda del test anterior: sin corregir, casi nada calza.

    Sin esto, un cambio que deshaga la corrección podría pasar desapercibido si
    el test de arriba se volviera trivialmente cierto.
    """
    crudo = _df_crudo().set_index("date")["close"]
    calzan = sum(
        1 for f, v in BLOOMBERG.items()
        if pd.Timestamp(f) in crudo.index and abs(crudo.loc[pd.Timestamp(f)] - v) < 1e-9
    )
    assert calzan <= 1, f"el crudo calza en {calzan} fechas; el desfase ya no existiría"


def test_el_desplome_de_castillo_cae_el_lunes():
    """La prueba económica: el desplome es el LUNES 2021-06-07, no el martes.

    La segunda vuelta fue el domingo 2021-06-06. El mercado reacciona el primer
    día hábil siguiente. Si el retorno más negativo cae el martes, el panel va
    un día tarde y CUALQUIER alineación con macro o noticias está corrida.
    """
    out = corrige_etiqueta_bvl(_df_crudo()).set_index("date")["close"]
    ret = out.pct_change()
    peor = ret.idxmin()
    assert peor == pd.Timestamp("2021-06-07"), f"el desplome quedó en {peor.date()}"
    assert ret.loc[peor] < -0.14, f"magnitud inesperada: {ret.loc[peor]:.2%}"


def test_no_inventa_filas_ni_reordena():
    crudo = _df_crudo()
    out = corrige_etiqueta_bvl(crudo)
    assert len(out) == len(crudo) - 1, "debe perderse exactamente una fila"
    assert out["date"].is_monotonic_increasing
    # Se descarta el PRIMER cierre: su fecha verdadera es anterior al rango
    # pedido, y por eso `fetch_bvl` pide un colchón de días hacia atrás.
    assert list(out["close"]) == [c for _, c in CRUDO_BVL][1:]


def test_vacio_no_revienta():
    vacio = pd.DataFrame({"date": pd.to_datetime([]), "close": []})
    assert corrige_etiqueta_bvl(vacio).empty


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
