# -*- coding: utf-8 -*-
"""Caracteriza el REGIMEN de mercado de cada tramo de la particion (D10).

POR QUE EXISTE. El informe de avance y la presentacion rotulan los pliegues
("año alcista", "pandemia y elecciones", "año bajista"), y resultados_entorno_OE1
§6.1 llego a afirmar que la validacion del pliegue 0 fue "el mejor año de la
decada". Esa frase se escribio comparando SOLO los seis tramos de la particion
y se generalizo sin medirla; medida, es falsa. Este script deja la medicion
reproducible.

QUE MIDE. Un indice EQUIPONDERADO de los 7 activos, rebalanceado a diario,
BRUTO (sin costos ni caja), sobre la valuacion total-return del panel. Es una
medida SOBRE NUESTRO PROPIO UNIVERSO, no un indice externo: el indice local de
retorno total (SPBLPGPT) sigue pendiente en D10.

EL TRAMO CIEGO NO SE TOCA. El test del pliegue 2 es el unico tramo que ningun
pliegue usa para entrenar ni validar; el registro de D10 exige con_test = 0.
Por eso las ventanas moviles y los años calendario se cortan ANTES de que
empiece. Los tests de los pliegues 0 y 1 si entran, porque son train de los
pliegues siguientes.

Uso:
    python scripts/caracteriza_pliegues.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.env import load_panel  # noqa: E402
from src.env.folds import walk_forward  # noqa: E402

WARMUP = 250
DIAS = 252


def resumen(r: np.ndarray) -> tuple[float, float, float]:
    """Retorno total, volatilidad anualizada y maxima caida de una serie diaria."""
    v = np.cumprod(1.0 + r)
    ret = float(v[-1] - 1.0)
    vol = float(np.std(r, ddof=1) * np.sqrt(DIAS))
    pico = np.maximum.accumulate(np.concatenate([[1.0], v]))[1:]
    dd = float(np.min(v / pico - 1.0))
    return ret, vol, dd


def main() -> None:
    panel = load_panel(view="solo_mercado", warmup=WARMUP)
    primer_util = max(panel.features.warmup + 1, panel.first_tradable_index)
    folds = walk_forward(panel.n_steps, n_folds=3, start=primer_util)

    precios = panel.prices
    r_act = precios[1:] / precios[:-1] - 1.0
    # r_idx[t] = retorno del dia t (de t-1 a t); r_idx[0] no existe.
    r_idx = np.concatenate([[np.nan], np.nanmean(r_act, axis=1)])
    fechas = panel.dates

    ciego = folds[-1].test[0]  # primer dia del tramo que no se mira

    print("=" * 78)
    print("REGIMEN DE CADA TRAMO — indice equiponderado de los 7, bruto")
    print("=" * 78)
    print(f"{'tramo':<16} {'desde':>11} {'hasta':>11} {'ret':>8} {'vol':>7} {'maxDD':>8}")
    for p in folds:
        for tramo in ("train", "val"):
            a, b = p.rango(tramo)
            ret, vol, dd = resumen(r_idx[a + 1:b])
            d0, d1 = p.fechas(fechas, tramo)
            print(f"pliegue {p.idx} {tramo:<6} {d0:>11} {d1:>11} "
                  f"{ret:>+8.1%} {vol:>7.1%} {dd:>+8.1%}")

    # ---- ¿que tan bueno fue el tramo de val del pliegue 0? ----
    ini = primer_util
    fins = np.arange(ini + DIAS, ciego)  # ventana (fin-252, fin], toda antes del ciego
    ventanas = np.array([np.prod(1.0 + r_idx[f - DIAS + 1:f + 1]) - 1.0 for f in fins])
    print(f"\n{'=' * 78}")
    print(f"VENTANAS DE {DIAS} DIAS ENTRE {str(fechas[ini])[:10]} Y "
          f"{str(fechas[ciego - 1])[:10]}  (n = {len(ventanas):,})")
    print("=" * 78)
    for p in folds:
        a, b = p.val
        ret_val = np.prod(1.0 + r_idx[a + 1:b]) - 1.0
        pct = float(np.mean(ventanas <= ret_val))
        print(f"  val pliegue {p.idx}: {ret_val:>+7.1%}  -> percentil {pct:.0%}")
    k = int(np.argmax(ventanas))
    print(f"  mejor ventana:   {ventanas[k]:>+7.1%}  termina el {str(fechas[fins[k]])[:10]}")
    print(f"  mediana:         {np.median(ventanas):>+7.1%}")

    # ---- por año calendario, solo años completos antes del ciego ----
    print(f"\n{'=' * 78}")
    print("POR AÑO CALENDARIO (años completos antes del tramo ciego)")
    print("=" * 78)
    anios = fechas.astype("datetime64[Y]").astype(int) + 1970
    ult_completo = int(anios[ciego]) - 1
    for y in range(int(anios[ini]), ult_completo + 1):
        m = (anios == y) & (np.arange(len(fechas)) > ini)
        print(f"  {y}: {np.prod(1.0 + r_idx[m]) - 1.0:>+7.1%}")


if __name__ == "__main__":
    main()
