"""OE1 — partición walk-forward con purga y embargo (D10).

Por qué walk-forward y no un corte único: con 2013-2025 el corte obvio
(train 2013-2019, val 2020-2021, test 2022-2025) mete la pandemia y Castillo
enteros en validación, que es el régimen más raro de los catorce años. Con
pliegues, cada uno ES un régimen distinto y se reportan todos — que además
contesta gratis la pregunta del especialista sobre quiebres de régimen, en vez
de discutir qué subperíodo excluir.

EL EMBARGO NO ES ADORNO. Las features llevan ventanas móviles (medias de 20/50
días, EWMAs de 60, volatilidad de 20) y los fundamentales son escalones
trimestrales. Sin un hueco entre tramos, la última observación de entrenamiento
y la primera de validación comparten insumos, y el modelo ve por la ventana. El
embargo por defecto (20 días) cubre la ventana móvil más larga del canal de
mercado; si algún día entra una feature con ventana mayor, hay que subirlo.

REGLA DE ORO DEL MVP (D21): el tramo de PRUEBA no se toca. El piloto entrena en
`train` y diagnostica en `val`. `test` existe acá para poder EXCLUIRLO de forma
explícita, no para mirarlo.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

EMBARGO_DEFAULT = 20


@dataclass(frozen=True)
class Fold:
    """Un pliegue: índices de inicio (inclusive) y fin (exclusivo) por tramo."""

    idx: int
    train: tuple[int, int]
    val: tuple[int, int]
    test: tuple[int, int]

    def rango(self, tramo: str) -> tuple[int, int]:
        return {"train": self.train, "val": self.val, "test": self.test}[tramo]

    def fechas(self, dates: np.ndarray, tramo: str) -> tuple[str, str]:
        a, b = self.rango(tramo)
        return str(dates[a])[:10], str(dates[b - 1])[:10]

    def describe(self, dates: np.ndarray) -> str:
        partes = []
        for tramo in ("train", "val", "test"):
            a, b = self.rango(tramo)
            d0, d1 = self.fechas(dates, tramo)
            partes.append(f"{tramo} {d0}..{d1} ({b - a}d)")
        return f"pliegue {self.idx}: " + " | ".join(partes)


def walk_forward(
    n_dates: int,
    n_folds: int = 3,
    val_len: int = 252,
    test_len: int = 504,
    embargo: int = EMBARGO_DEFAULT,
    min_train: int = 756,
    start: int = 0,
    train_len: int | None = None,
) -> list[Fold]:
    """Pliegues con validación/prueba deslizándose y entrenamiento EXPANDIENDO.

    El entrenamiento de cada pliegue arranca siempre al principio del historial
    y termina justo antes de su validación: es cómo se usaría el modelo en la
    práctica —reentrenar con todo lo conocido hasta la fecha—, y evita el sesgo
    de una ventana de entrenamiento arbitrariamente corta al final.

    VENTANA MÓVIL (`train_len`), añadida el 2026-09-11 tras la observación del
    asesor: si el mercado cambia de régimen, la data vieja deja de describir el
    presente y arrastrarla puede ser peor que descartarla. Con `train_len=N` el
    entrenamiento es una ventana FIJA de N días que se desplaza (rolling) en vez
    de crecer (expanding).

    NO HAY UN DEFAULT "BUENO" ACÁ, Y POR ESO NO SE CAMBIA EL EXISTENTE. Las dos
    opciones se contradicen entre sí:
      * expanding aprovecha todo el historial, que con ~3,260 días utilizables es
        el recurso escaso de este problema;
      * rolling responde al cambio de régimen, pero en el pliegue 2 descarta el
        41% de su entrenamiento.
    Es una decisión PRE-REGISTRABLE, no un hiperparámetro a elegir mirando la
    validación (ver D22: eso sería selección encubierta y entraría al contador
    de D10).

    Args:
        n_dates: largo del calendario disponible.
        n_folds: cuántos pliegues.
        val_len, test_len: días de validación y prueba por pliegue.
        embargo: días descartados entre tramos.
        min_train: mínimo de días de entrenamiento del primer pliegue.
        start: primer índice utilizable. NO es cosmético: si se deja en 0, el
            pliegue dice que entrena desde 2012-01-02 cuando el entorno en
            realidad arranca después del calentamiento de D6 y de que InRetail
            salga a bolsa. Un rótulo que miente termina siendo una frase
            equivocada en la tesis. Pasar `max(warmup + 1, first_tradable)`.
        train_len: None -> entrenamiento EXPANDIENDO (comportamiento histórico).
            Un entero -> ventana MÓVIL de ese largo. Nunca se retrocede antes de
            `start`, así que el primer pliegue puede quedar más corto que `N`.
    """
    if n_folds < 1:
        raise ValueError("n_folds debe ser >= 1")
    if train_len is not None and train_len < min_train:
        raise ValueError(
            f"train_len={train_len} es menor que min_train={min_train}: la ventana "
            "móvil no puede ser más corta que el mínimo exigido de entrenamiento."
        )
    folds: list[Fold] = []
    for k in range(n_folds):
        test_end = n_dates - (n_folds - 1 - k) * test_len
        test_start = test_end - test_len
        val_end = test_start - embargo
        val_start = val_end - val_len
        train_end = val_start - embargo
        train_start = start if train_len is None else max(start, train_end - train_len)
        if train_end - train_start < min_train:
            raise ValueError(
                f"el pliegue {k} deja solo {max(train_end - train_start, 0)} días de "
                f"entrenamiento (mínimo {min_train}). Reduce n_folds, val_len o test_len."
            )
        folds.append(
            Fold(
                idx=k,
                train=(train_start, train_end),
                val=(val_start, val_end),
                test=(test_start, test_end),
            )
        )
    return folds
