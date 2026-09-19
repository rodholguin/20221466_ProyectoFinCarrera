"""Tests de la partición walk-forward (D10).

Los pliegues son donde se cuela un look-ahead sin que nada falle: basta que la
validación empiece un día antes de tiempo para que las ventanas móviles de 20 y
60 días compartan insumos con el entrenamiento. Estos tests fijan el contrato.

    python tests/test_folds.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.env.folds import EMBARGO_DEFAULT, walk_forward


def test_hay_embargo_entre_todos_los_tramos():
    for f in walk_forward(3513, n_folds=3, embargo=EMBARGO_DEFAULT):
        assert f.val[0] - f.train[1] >= EMBARGO_DEFAULT, (
            f"pliegue {f.idx}: sin embargo entre entrenamiento y validación"
        )
        assert f.test[0] - f.val[1] >= EMBARGO_DEFAULT, (
            f"pliegue {f.idx}: sin embargo entre validación y prueba"
        )


def test_los_tramos_no_se_solapan_dentro_de_un_pliegue():
    for f in walk_forward(3513, n_folds=3):
        rangos = [f.train, f.val, f.test]
        for (a0, a1), (b0, b1) in zip(rangos, rangos[1:]):
            assert a1 <= b0, f"pliegue {f.idx}: tramos solapados {(a0, a1)} y {(b0, b1)}"
        assert f.train[1] > f.train[0] and f.val[1] > f.val[0] and f.test[1] > f.test[0]


def test_el_entrenamiento_expande_y_los_pliegues_avanzan():
    folds = walk_forward(3513, n_folds=3)
    for a, b in zip(folds, folds[1:]):
        assert b.train[1] > a.train[1], "el entrenamiento no expande entre pliegues"
        assert b.val[0] > a.val[0], "la validación no avanza en el tiempo"
        assert b.test[0] > a.test[0], "la prueba no avanza en el tiempo"


def test_ventana_movil_mantiene_el_largo_y_descarta_lo_viejo():
    # La opción `train_len` (2026-09-11, observación del asesor sobre cambio de
    # régimen): el entrenamiento deja de crecer y se DESPLAZA. El contrato es que
    # el largo sea constante y que el inicio avance, no solo el final.
    folds = walk_forward(3513, n_folds=3, start=251, train_len=1458)
    for f in folds[1:]:
        assert f.train[1] - f.train[0] == 1458, (
            f"pliegue {f.idx}: la ventana móvil cambió de largo"
        )
    for a, b in zip(folds, folds[1:]):
        assert b.train[0] > a.train[0], "la ventana móvil no descarta datos viejos"


def test_ventana_movil_nunca_retrocede_antes_del_primer_indice_utilizable():
    # El primer pliegue puede quedar MÁS CORTO que la ventana pedida: no se puede
    # entrenar con días que no existen (calentamiento de D6 + IPO de InRetail).
    folds = walk_forward(3513, n_folds=3, start=251, train_len=1458)
    assert folds[0].train[0] == 251, "la ventana móvil retrocedió antes de `start`"


def test_expandir_es_el_default_y_no_cambio():
    # Guarda contra una deriva silenciosa: agregar `train_len` NO debe haber
    # movido el comportamiento histórico con el que se corrió el piloto de D21.
    assert walk_forward(3513, n_folds=3, start=251) == walk_forward(
        3513, n_folds=3, start=251, train_len=None
    )
    for f in walk_forward(3513, n_folds=3, start=251):
        assert f.train[0] == 251, "el default dejó de expandir desde `start`"


def test_ventana_movil_mas_corta_que_el_minimo_se_cae():
    try:
        walk_forward(3513, n_folds=3, start=251, train_len=500, min_train=756)
    except ValueError:
        return
    raise AssertionError("una ventana móvil menor que min_train debería fallar temprano")


def test_respeta_el_primer_indice_utilizable():
    # Si `start` se ignorara, el rótulo del pliegue diría que entrena desde el
    # primer día del panel, cuando el entorno arranca después del calentamiento
    # de D6 y de que todos los activos coticen.
    inicio = 251
    for f in walk_forward(3513, n_folds=3, start=inicio):
        assert f.train[0] == inicio, "el entrenamiento no arranca en el índice pedido"


def test_se_cae_si_no_alcanza_el_historial():
    try:
        walk_forward(900, n_folds=3, val_len=252, test_len=504, min_train=756)
    except ValueError as exc:
        assert "entrenamiento" in str(exc)
        return
    raise AssertionError("debería haberse caído: no hay historial para 3 pliegues")


def test_la_descripcion_usa_fechas_reales():
    fechas = np.array(
        [np.datetime64("2013-01-01") + np.timedelta64(i, "D") for i in range(3513)]
    )
    f = walk_forward(3513, n_folds=3, start=251)[0]
    texto = f.describe(fechas)
    assert str(fechas[251])[:10] in texto, "la descripción no refleja el inicio real"
    assert "train" in texto and "val" in texto and "test" in texto


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
    print("\n" + ("todos los tests pasaron" if not fallos else f"{fallos} test(s) con problemas"))
    sys.exit(1 if fallos else 0)
