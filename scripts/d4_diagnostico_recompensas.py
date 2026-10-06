# -*- coding: utf-8 -*-
"""D4 — QUÉ PREMIA CADA RECOMPENSA. Diagnóstico sin entrenar.

POR QUÉ ESTE SCRIPT EXISTE. §7.9 dejó medido que entrenar más EMPEORA la
validación y que el mecanismo visible es la rotación. Lo que NO estaba medido es
POR QUÉ el objetivo pide rotar. Eso no hace falta entrenarlo: se lee de la forma
funcional del DSR y se verifica sobre series de retorno REALES del propio
simulador. Entrenar para explicar una recompensa mide el agente, no la
recompensa.

LA HIPÓTESIS, Y ES ANALÍTICA. Reordenando el DSR de Moody-Saffell:

    r_t = [ B·(R−A) − ½·A·(R²−B) ] / V^{3/2}
        = (B / V^{3/2}) · [ (R−A) − (A / 2B)·(R²−B) ]

El castigo al retorno al cuadrado NO es una constante: es **A/(2B)**, o sea
PROPORCIONAL A LA MEDIA MÓVIL DEL PROPIO RETORNO. De ahí salen dos predicciones
que este script contrasta:

  H1. Si A < 0 el coeficiente cambia de signo y el DSR **PAGA** por varianza.
      En un tramo perdedor el objetivo premia tomar MÁS riesgo.
  H2. Aun con A > 0, a frecuencia diaria (A/2B)·R² es de segundo orden frente a
      (R−A). Si eso es así, el DSR se comporta casi como un maximizador de
      retorno bruto y su "ajuste por riesgo" es decorativo en este mercado.

H2 es la que explica D25: si el término de riesgo no muerde, optimizar más
tiempo el DSR es optimizar más tiempo el retorno de corto plazo, y explotar
patrones de corto plazo EXIGE operar. El peaje se paga dentro de R_t, pero entra
con peso 1 contra un término de riesgo que vale centésimas.

ESTO IMPORTA PARA CITAR LITERATURA. El DSR se propuso sobre mercados con deriva
positiva (Moody-Saffell, S&P y FX de los 90). Con A ≈ 0 —o negativo, como la BVL
2013-2018— su término de riesgo degenera. No es que la recompensa esté mal
implementada: está evaluada fuera del régimen donde fue diseñada. Eso es
exactamente lo que impide comparar resultados con la literatura de frente.

Uso:
    python scripts/d4_diagnostico_recompensas.py
    python scripts/d4_diagnostico_recompensas.py --fold 1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.env import (  # noqa: E402
    CashOnly,
    EnvConfig,
    EqualWeight,
    Markowitz,
    PortfolioEnv,
    load_panel,
    run_policy,
    snapshot_cost_model,
)
from src.env.folds import walk_forward  # noqa: E402
from src.env.rewards import make_reward  # noqa: E402

SALIDA = Path("data/interim/artefactos_oe1/d4_diagnostico_recompensas.json")
WARMUP = 250
ETA = 1.0 / 60.0
DIAS = 252


# --------------------------------------------------------------------------- #
# 1. Series de retorno REALES. No se simulan: salen del mismo simulador que
#    produce los resultados de la tesis, con sus costos y su máscara.
# --------------------------------------------------------------------------- #
def series_reales(panel, costos, rango) -> dict:
    out = {}
    for etiqueta, pol, freq in [
        ("1/N diario", EqualWeight(), 1),
        ("1/N mensual", EqualWeight(), 21),
        ("solo caja", CashOnly(), 1),
        ("markowitz", Markowitz(window=252, min_obs=60), 21),
    ]:
        env = PortfolioEnv(
            panel, costos,
            EnvConfig(action_mode="weights", rebalance_every=freq,
                      start_index=rango[0], end_index=rango[1]),
        )
        out[etiqueta] = np.asarray(run_policy(env, pol)["returns"], dtype=float)
    return out


# --------------------------------------------------------------------------- #
# 2. Descomposición del DSR paso a paso. Es la pieza central.
# --------------------------------------------------------------------------- #
def descompone_dsr(r: np.ndarray, eta: float = ETA) -> dict:
    """Separa cada r_t en su término de RETORNO y su término de VARIANZA.

    Devuelve además el coeficiente implícito A/(2B) —el precio que el DSR le
    pone a la varianza— y cuántos días ese precio sale NEGATIVO, o sea días en
    que el objetivo paga por dispersión en vez de castigarla.
    """
    a = b = 0.0
    t_ret, t_var, coef = [], [], []
    for x in r:
        var = b - a * a
        if var > 1e-8:
            v15 = var ** 1.5
            t_ret.append(b * (x - a) / v15)
            t_var.append(-0.5 * a * (x * x - b) / v15)
            coef.append(a / (2.0 * b) if b > 0 else np.nan)
        a += eta * (x - a)
        b += eta * (x * x - b)
    t_ret = np.asarray(t_ret, dtype=float)
    t_var = np.asarray(t_var, dtype=float)
    coef = np.asarray(coef, dtype=float)
    masa_ret = float(np.sum(np.abs(t_ret)))
    masa_var = float(np.sum(np.abs(t_var)))
    return {
        "pasos_activos": int(t_ret.size),
        "suma_termino_retorno": float(np.sum(t_ret)),
        "suma_termino_varianza": float(np.sum(t_var)),
        # Cuánto del MOVIMIENTO de la recompensa explica cada término. Se usa
        # masa absoluta y no suma con signo porque los dos se cancelan solos.
        "peso_varianza_en_la_senial": masa_var / (masa_ret + masa_var + 1e-12),
        # H1: días en que el precio de la varianza es negativo = días en que
        # MÁS DISPERSIÓN ES MÁS RECOMPENSA.
        "frac_dias_coef_negativo": float(np.mean(coef < 0)),
        "frac_dias_premia_varianza": float(np.mean(t_var > 0)),
        "coef_mediano": float(np.nanmedian(coef)),
        "coef_p10": float(np.nanpercentile(coef, 10)),
        "coef_p90": float(np.nanpercentile(coef, 90)),
    }


def acumula(r: np.ndarray, nombre: str) -> float:
    # logret no tiene estadisticos exponenciales, asi que no acepta eta.
    rec = make_reward(nombre) if nombre == "logret" else make_reward(nombre, eta=ETA)
    rec.reset()
    return float(np.sum([rec.step(float(x)) for x in r]))


# --------------------------------------------------------------------------- #
# 3. Prueba pareada: MISMA MEDIA, MÁS VOLATILIDAD.
#    r' = m + k·(r − m) conserva la media EXACTA y multiplica la desviación por
#    k. Si la recompensa acumulada SUBE, el objetivo prefiere el ruido.
# --------------------------------------------------------------------------- #
def prueba_vol(r: np.ndarray, factores=(1.25, 1.5, 2.0)) -> dict:
    m = float(np.mean(r))
    base = {n: acumula(r, n) for n in ("dsr", "ddr", "logret")}
    out = {"media_diaria": m, "vol_anual": float(np.std(r) * np.sqrt(DIAS)),
           "base": base, "inflada": {}}
    for k in factores:
        rk = m + k * (r - m)
        out["inflada"][f"k={k}"] = {
            "vol_anual": float(np.std(rk) * np.sqrt(DIAS)),
            **{n: acumula(rk, n) - base[n] for n in ("dsr", "ddr", "logret")},
        }
    return out


# --------------------------------------------------------------------------- #
# 4. ¿CUÁNTO PEAJE COMPRA ESA VOLATILIDAD? Se resta un lastre constante de c
#    puntos base por día —que es exactamente lo que hace rotar más— y se busca
#    el c que anula la ganancia de recompensa de haber inflado la vol.
# --------------------------------------------------------------------------- #
def precio_del_peaje(r: np.ndarray, k: float = 1.5, nombre: str = "dsr") -> dict:
    m = float(np.mean(r))
    rk = m + k * (r - m)
    ganancia = acumula(rk, nombre) - acumula(r, nombre)
    if ganancia <= 0:
        return {"ganancia_por_inflar_vol": ganancia,
                "peaje_indiferente_bps_dia": 0.0,
                "peaje_indiferente_pp_anual": 0.0,
                "nota": "inflar la vol NO sube la recompensa"}
    lo, hi = 0.0, 50.0  # bps por día
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if acumula(rk - mid * 1e-4, nombre) - acumula(r, nombre) > 0:
            lo = mid
        else:
            hi = mid
    return {
        "ganancia_por_inflar_vol": ganancia,
        "peaje_indiferente_bps_dia": lo,
        "peaje_indiferente_pp_anual": lo * 1e-4 * DIAS * 100.0,
        "nota": "",
    }


# --------------------------------------------------------------------------- #
# 5. ¿LA SUMA DE INCREMENTOS ES "EL SHARPE DEL PERIODO"? Eso afirma el docstring
#    de src/env/rewards.py, y de ahí sale toda la legitimidad de usar el DSR
#    como recompensa por paso. Si fuera cierto, la suma acumulada tendría que
#    ordenar las estrategias igual que el Sharpe del tramo. Se contrasta.
# --------------------------------------------------------------------------- #
def telescopio(r: np.ndarray, eta: float = ETA) -> dict:
    """Compara la suma de DSR contra el Sharpe EWMA TERMINAL y el del periodo."""
    a = b = 0.0
    suma = 0.0
    for x in r:
        var = b - a * a
        if var > 1e-8:
            suma += (b * (x - a) - 0.5 * a * (x * x - b)) / var ** 1.5
        a += eta * (x - a)
        b += eta * (x * x - b)
    var_fin = max(b - a * a, 1e-12)
    sharpe_ewma_final = a / np.sqrt(var_fin)
    sharpe_periodo = float(np.mean(r) / (np.std(r) + 1e-12))
    return {
        "suma_dsr": float(suma),
        "sharpe_ewma_terminal_diario": float(sharpe_ewma_final),
        "sharpe_periodo_diario": sharpe_periodo,
        "sharpe_ewma_terminal_anual": float(sharpe_ewma_final * np.sqrt(DIAS)),
        "sharpe_periodo_anual": float(sharpe_periodo * np.sqrt(DIAS)),
        # Si la suma telescopa al Sharpe TERMINAL, esta razon es ~1/eta.
        "razon_suma_sobre_sharpe_terminal": float(suma / (sharpe_ewma_final + 1e-12)),
        "uno_sobre_eta": 1.0 / eta,
    }


# --------------------------------------------------------------------------- #
# 6. LA PREGUNTA DE D25, DIRECTA: ¿el objetivo PREFIERE al agente que valida
#    peor? Se toman los momentos MEDIDOS a 150k y a 1M pasos (§7.9) y se
#    construyen trayectorias con esos momentos reusando la FORMA de una serie
#    real. Si la recompensa acumulada del agente de 1M sale mayor, entonces
#    entrenar mas no fallo: cumplio el objetivo, y el objetivo estaba mal.
# --------------------------------------------------------------------------- #
MOMENTOS_D25 = {
    "150k pasos": {"ret": 0.030, "vol": 0.048},
    "300k pasos": {"ret": 0.010, "vol": 0.056},
    "600k pasos": {"ret": 0.019, "vol": 0.075},
    "1M pasos": {"ret": 0.014, "vol": 0.068},
}


def reescala(forma: np.ndarray, ret_anual: float, vol_anual: float) -> np.ndarray:
    """Misma FORMA, momentos impuestos. No inventa datos: reordena escala."""
    z = (forma - np.mean(forma)) / (np.std(forma) + 1e-12)
    mu_d = (1.0 + ret_anual) ** (1.0 / DIAS) - 1.0
    sd_d = vol_anual / np.sqrt(DIAS)
    return mu_d + sd_d * z


def d25_directo(forma: np.ndarray, semillas: int = 200, rng_seed: int = 0) -> dict:
    """Ranking por recompensa acumulada de los cuatro presupuestos de D25.

    Se bootstrapea la FORMA (remuestreo por bloques de 21 dias) para que el
    veredicto no dependa de una sola ordenacion de los dias.
    """
    rng = np.random.default_rng(rng_seed)
    n = forma.size
    bloques = max(n // 21, 1)
    gana = {k: 0 for k in MOMENTOS_D25}
    acum = {k: [] for k in MOMENTOS_D25}
    for _ in range(semillas):
        idx = rng.integers(0, max(n - 21, 1), size=bloques)
        muestra = np.concatenate([forma[i:i + 21] for i in idx])
        valores = {}
        for etiqueta, m in MOMENTOS_D25.items():
            serie = reescala(muestra, m["ret"], m["vol"])
            v = acumula(serie, "dsr")
            valores[etiqueta] = v
            acum[etiqueta].append(v)
        gana[max(valores, key=valores.get)] += 1
    ref = "150k pasos"
    pareado = {}
    for k in MOMENTOS_D25:
        if k == ref:
            continue
        d = np.asarray(acum[k]) - np.asarray(acum[ref])
        pareado[k] = {
            "mediana_dsr_menos_150k": float(np.median(d)),
            "frac_supera_a_150k": float(np.mean(d > 0)),
        }
    return {
        "veces_que_gana": gana,
        "dsr_acumulado_mediano": {k: float(np.median(v)) for k, v in acum.items()},
        # El argmax y la mediana marginal pueden contradecirse con variables
        # correlacionadas y sesgadas; lo que decide es la diferencia PAREADA.
        "pareado_contra_150k": pareado,
        "n_bootstrap": semillas,
    }


# --------------------------------------------------------------------------- #
# 7. EL DENOMINADOR. r_t lleva V^{-3/2}: cuando la ventana viene CALMA, V es
#    chico y CUALQUIER dia bueno paga una barbaridad. Si la masa de recompensa
#    se concentra en los dias que siguen a tramos calmos, entonces el objetivo
#    no premia "ganar": premia GANAR DESPUES DE ESTAR QUIETO. Y la forma de
#    producir eso es irse a caja y volver concentrado — o sea, OPERAR.
# --------------------------------------------------------------------------- #
def concentracion(r: np.ndarray, eta: float = ETA) -> dict:
    a = b = 0.0
    rr, vv = [], []
    for x in r:
        var = b - a * a
        if var > 1e-8:
            rr.append((b * (x - a) - 0.5 * a * (x * x - b)) / var ** 1.5)
            vv.append(var)
        a += eta * (x - a)
        b += eta * (x * x - b)
    rr = np.asarray(rr, dtype=float)
    vv = np.asarray(vv, dtype=float)
    if rr.size == 0:
        return {}
    orden = np.argsort(vv)           # de la ventana mas calma a la mas agitada
    n10 = max(int(0.10 * rr.size), 1)
    calmos = orden[:n10]
    total_abs = float(np.sum(np.abs(rr))) + 1e-12
    return {
        "n": int(rr.size),
        # Que fraccion del MOVIMIENTO de la recompensa ocurre en el 10% de dias
        # con la ventana mas calma. Si fuera proporcional, seria 10%.
        "masa_en_decil_mas_calmo": float(np.sum(np.abs(rr[calmos])) / total_abs),
        "suma_en_decil_mas_calmo": float(np.sum(rr[calmos])),
        "suma_total": float(np.sum(rr)),
        # Cuantas veces mas grande es |r| en el decil calmo que en el agitado.
        "razon_calmo_sobre_agitado": float(
            np.mean(np.abs(rr[calmos])) / (np.mean(np.abs(rr[orden[-n10:]])) + 1e-12)
        ),
        "corr_recompensa_vs_varianza": float(np.corrcoef(np.abs(rr), vv)[0, 1]),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fold", type=int, default=0)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--out", default=str(SALIDA))
    args = ap.parse_args()

    panel = load_panel(view="solo_mercado", warmup=WARMUP)
    costos = snapshot_cost_model(panel.tickers)
    primer_util = max(panel.features.warmup + 1, panel.first_tradable_index)
    pliegues = walk_forward(panel.n_steps, n_folds=args.folds, start=primer_util)
    p = pliegues[args.fold]

    print("=" * 86)
    print(f"D4 — QUE PREMIA CADA RECOMPENSA  ·  pliegue {p.idx}  ·  eta = 1/60")
    print("=" * 86)

    res = {"eta": ETA, "fold": p.idx, "tramos": {}}

    for tramo in ("train", "val"):
        rango = p.rango(tramo)
        f0, f1 = panel.dates[rango[0]], panel.dates[rango[1] - 1]
        print(f"\n{'=' * 86}\nTRAMO {tramo.upper()}   {f0}  ->  {f1}\n{'=' * 86}")
        series = series_reales(panel, costos, rango)
        # "solo caja" tiene varianza cero por construccion (D9): el DSR nunca
        # sale del calentamiento y no hay nada que descomponer. Se excluye de
        # las pruebas en vez de ensuciarlas con NaN.
        # El umbral es de VOL ANUAL, no de std cruda: 'solo caja' tiene
        # dispersion diminuta pero no nula (la tasa BCRP se mueve), y con
        # ella el DSR nunca sale del calentamiento. No hay nada que medir.
        series = {k: v for k, v in series.items()
                  if float(np.std(v)) * np.sqrt(DIAS) > 1e-3}
        res["tramos"][tramo] = {"desde": str(f0), "hasta": str(f1), "series": {}}

        print("\n-- H1/H2: DE QUE ESTA HECHA LA SENAL DEL DSR " + "-" * 41)
        print(f"{'serie':<14} {'ret an':>7} {'vol an':>7} {'coefA/2B':>9} "
              f"{'%dias<0':>8} {'%premia':>8} {'peso var':>9}")
        for etiqueta, r in series.items():
            d = descompone_dsr(r)
            ret_an = float((1 + np.mean(r)) ** DIAS - 1)
            vol_an = float(np.std(r) * np.sqrt(DIAS))
            print(f"{etiqueta:<14} {ret_an:>+6.1%} {vol_an:>7.1%} "
                  f"{d['coef_mediano']:>9.3f} {d['frac_dias_coef_negativo']:>7.0%} "
                  f"{d['frac_dias_premia_varianza']:>7.0%} "
                  f"{d['peso_varianza_en_la_senial']:>8.2%}")
            res["tramos"][tramo]["series"][etiqueta] = {
                "ret_anual": ret_an, "vol_anual": vol_an, "descomposicion": d,
            }

        print("\n-- LA SUMA DE INCREMENTOS, CONTRA LOS DOS SHARPE " + "-" * 37)
        print(f"{'serie':<14} {'suma DSR':>10} {'Sh periodo':>11} {'Sh EWMA fin':>12} "
              f"{'suma/ShEWMA':>12}   (1/eta = 60)")
        for etiqueta, r in series.items():
            t = telescopio(r)
            res["tramos"][tramo]["series"][etiqueta]["telescopio"] = t
            print(f"{etiqueta:<14} {t['suma_dsr']:>10.1f} "
                  f"{t['sharpe_periodo_anual']:>+11.2f} "
                  f"{t['sharpe_ewma_terminal_anual']:>+12.2f} "
                  f"{t['razon_suma_sobre_sharpe_terminal']:>12.1f}")

        print("\n-- DONDE SE ACUMULA LA RECOMPENSA (denominador V^-3/2) " + "-" * 31)
        print(f"{'serie':<14} {'masa en 10% mas calmo':>22} {'|r| calmo/agitado':>19} {'corr |r| vs V':>15}")
        for etiqueta, r in series.items():
            c = concentracion(r)
            res["tramos"][tramo]["series"][etiqueta]["concentracion"] = c
            print(f"{etiqueta:<14} {c['masa_en_decil_mas_calmo']:>21.1%} "
                  f"{c['razon_calmo_sobre_agitado']:>18.1f}x "
                  f"{c['corr_recompensa_vs_varianza']:>+15.2f}")

        print("\n-- MISMA MEDIA, MAS VOLATILIDAD: sube la recompensa? " + "-" * 33)
        print(f"{'serie':<14} {'k':>5} {'vol an':>7} {'dDSR':>10} {'dDDR':>10} {'dLOGRET':>10}")
        for etiqueta, r in series.items():
            pv = prueba_vol(r)
            res["tramos"][tramo]["series"][etiqueta]["prueba_vol"] = pv
            for clave, v in pv["inflada"].items():
                k = clave.split("=")[1]
                print(f"{etiqueta:<14} {k:>5} {v['vol_anual']:>7.1%} "
                      f"{v['dsr']:>+10.1f} {v['ddr']:>+10.1f} {v['logret']:>+10.4f}")

        print("\n-- CUANTO PEAJE COMPRA ESA VOLATILIDAD? (k=1.5, DSR) " + "-" * 33)
        print(f"{'serie':<14} {'bps/dia':>9} {'pp anual':>9}   nota")
        for etiqueta, r in series.items():
            pp = precio_del_peaje(r)
            res["tramos"][tramo]["series"][etiqueta]["precio_peaje"] = pp
            print(f"{etiqueta:<14} {pp['peaje_indiferente_bps_dia']:>9.2f} "
                  f"{pp['peaje_indiferente_pp_anual']:>8.1f}%   {pp.get('nota', '')}")

    # --------------------------------------------------------------- D25
    print(f"\n{'=' * 86}")
    print("D25 DIRECTO: que presupuesto PREFIERE el DSR?")
    print("Momentos MEDIDOS en validacion (7.9). Forma: 1/N diario del tramo val.")
    print("=" * 86)
    forma = series_reales(panel, costos, p.rango("val"))["1/N diario"]
    d25 = d25_directo(np.asarray(forma, dtype=float))
    res["d25_directo"] = d25
    print(f"{'presupuesto':<14} {'ret val':>8} {'vol val':>8} {'DSR acum':>10} {'gana %':>8}")
    for etiqueta, m in MOMENTOS_D25.items():
        print(f"{etiqueta:<14} {m['ret']:>+7.1%} {m['vol']:>8.1%} "
              f"{d25['dsr_acumulado_mediano'][etiqueta]:>10.2f} "
              f"{d25['veces_que_gana'][etiqueta] / d25['n_bootstrap']:>7.0%}")

    print("")
    print("PAREADO contra 150k (la comparacion que decide):")
    for k, v in d25["pareado_contra_150k"].items():
        print(f"  {k:<12} mediana DSR - DSR(150k) = {v['mediana_dsr_menos_150k']:+7.2f}   supera a 150k en {v['frac_supera_a_150k']:.0%} de las muestras")

    salida = Path(args.out)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nartefacto: {salida}")


if __name__ == "__main__":
    main()
