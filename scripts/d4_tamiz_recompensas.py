# -*- coding: utf-8 -*-
"""D4 — TAMIZ DE RECOMPENSAS. Se elige sin entrenar y SIN gastar el contador.

EL PROBLEMA QUE RESUELVE. D4 dice "tres brazos y no más" porque cada brazo que
se entrena es una configuración más en el contador de D10 y degrada el Sharpe
deflactado de la evaluación final. Con eso, probar recompensas nuevas parecía
caro por definición. No lo es: CARACTERIZAR UNA RECOMPENSA NO NECESITA UN
AGENTE, necesita series de retorno. El tamiz corre sobre estrategias reales
—dentro del mismo simulador, con sus costos y su máscara— y no entrena nada,
así que no anota ninguna configuración. Solo lo que PASA el tamiz se lleva
corridas.

EL CRITERIO, PRE-REGISTRADO EL 2026-09-19 ANTES DE MIRAR NINGÚN RESULTADO.
Una recompensa es admisible si cumple las cuatro:

  T1  FIDELIDAD DE ORDEN. Su valor acumulado tiene que ordenar estrategias
      reales igual que la métrica con la que el documento las va a juzgar.
      Se mide con la rho de Spearman contra el Sharpe del periodo, EN LOS DOS
      TRAMOS. Umbral: rho >= +0.50 en train y en val.
      >> Es el que el DSR REPRUEBA hoy (§7.11): en train le paga 5.7 veces más
         a Markowitz, que pierde plata, que al 1/N, que gana.

  T2  NO PAGA POR RUIDO. Inflar la volatilidad a media constante (k=1.5) no
      puede SUBIR el acumulado en ninguna serie del banco.
      >> Es el que la DDR reprueba hoy.

  T3  EL RIESGO PESA. El término de riesgo debe explicar al menos el 20% del
      movimiento de la señal. El DSR da 7-10%: reprueba.
      (Para las recompensas sin descomposición analítica cerrada se mide por
      ablación: cuánto cambia el acumulado al apagar el término de riesgo.)

  T4  VE EL PEAJE. Restar un lastre de 1 punto base por día —que es el orden de
      magnitud del costo de rotar -- tiene que bajar el acumulado de forma
      monótona y no despreciable (>= 1% del acumulado por cada bp/día).

NINGUNA DE LAS CUATRO MIRA A UN AGENTE. Son propiedades de la recompensa.

EL BANCO DE ESTRATEGIAS. 18 políticas reales sobre el mismo tramo: 1/N a tres
frecuencias, los tres Markowitz, comprar y mantener cada uno de los 7 activos,
y 5 carteras de la banda nula. Con tres estrategias, como en el diagnóstico,
una correlación de orden no significa nada; con 18 sí.

Uso:
    python scripts/d4_tamiz_recompensas.py
    python scripts/d4_tamiz_recompensas.py --fold 1
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
    FixedWeights,
    Markowitz,
    PortfolioEnv,
    RandomDirichlet,
    load_panel,
    run_policy,
    snapshot_cost_model,
)
from src.env.folds import walk_forward  # noqa: E402
from src.env.rewards import make_reward  # noqa: E402

SALIDA = Path("data/interim/artefactos_oe1/d4_tamiz_recompensas.json")
WARMUP = 250
ETA = 1.0 / 60.0
DIAS = 252

#: Umbrales del tamiz. SE FIJAN ACÁ, EN EL CÓDIGO, ANTES DE CORRERLO.
UMBRAL_T1_RHO = 0.50
UMBRAL_T3_PESO_RIESGO = 0.20
UMBRAL_T4_CAIDA_POR_BP = 0.01


def banco(panel, costos, rango) -> dict:
    """18 estrategias reales, todas dentro del mismo simulador."""
    n = panel.n_assets
    pols: list[tuple[str, object, int]] = [
        ("1/N diario", EqualWeight(), 1),
        ("1/N mensual", EqualWeight(), 21),
        ("1/N trimestral", EqualWeight(), 63),
        ("mkw tangencia", Markowitz(window=252, min_obs=60), 21),
        ("mkw tang-LW", Markowitz(window=252, min_obs=60, shrinkage="ledoit_wolf"), 21),
        ("mkw min-var", Markowitz(window=252, min_obs=60, objetivo="min_var"), 21),
        ("solo caja", CashOnly(), 1),
    ]
    for i, tk in enumerate(panel.tickers):
        w = np.zeros(n + 1)
        w[i] = 1.0
        pols.append((f"comprar {tk}", FixedWeights(w, name=f"bh_{tk}"), 21))
    for s in range(5):
        pols.append((f"azar s{s}", RandomDirichlet(seed=s), 21))

    out = {}
    for etiqueta, pol, freq in pols:
        env = PortfolioEnv(
            panel, costos,
            EnvConfig(action_mode="weights", rebalance_every=freq,
                      start_index=rango[0], end_index=rango[1]),
        )
        res = run_policy(env, pol)
        r = np.asarray(res["returns"], dtype=float)
        s = res["summary"]
        out[etiqueta] = {
            "retornos": r,
            "rotacion": np.asarray(env.history["turnover"], dtype=float),
            "sharpe_periodo": float(np.mean(r) / (np.std(r) + 1e-12) * np.sqrt(DIAS)),
            "retorno_total": float(s["retorno_total"]),
            "max_drawdown": float(s["max_drawdown"]),
            "rotacion_anual": float(s["rotacion_anual"]),
        }
    return out


def acumula(r: np.ndarray, nombre: str, rot: np.ndarray | None = None, **kw) -> float:
    rec = make_reward(nombre, **kw)
    rec.reset()
    if rot is None:
        rot = np.zeros_like(r)
    return float(np.sum([rec.step(float(x), float(t)) for x, t in zip(r, rot)]))


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    def rango(v):
        o = np.argsort(np.argsort(v))
        return o.astype(float)
    a, b = rango(x), rango(y)
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else 0.0


def calibra_escala(series: list[np.ndarray], forma: str) -> float:
    """Fija λ (o κ) para que el término de riesgo pese ~25% de la señal.

    ES LA REGLA DE D4(a), la de la propuesta del 2026-09-02: calibrar por
    ESCALA contra la magnitud media del 1/N, no contra resultados. Se recalcula
    con los datos que haya en vez de quedar fija en el código, que es la trampa
    que este proyecto ya pisó tres veces.
    """
    objetivo = 0.25
    r = np.concatenate(series)
    base = float(np.mean(np.abs(np.log1p(np.clip(r, -0.999, None)))))
    if forma == "mv":
        a = 0.0
        devs = []
        for x in r:
            devs.append((x - a) ** 2)
            a += ETA * (x - a)
        riesgo = float(np.mean(devs))
    elif forma == "logret_dd":
        v = pico = 1.0
        dd = 0.0
        incs = []
        for x in r:
            v *= 1.0 + x
            pico = max(pico, v)
            nuevo = 1.0 - v / pico
            incs.append(max(0.0, nuevo - dd))
            dd = nuevo
        riesgo = float(np.mean(incs))
    else:
        raise ValueError(forma)
    # lam tal que  lam*riesgo / (base + lam*riesgo) = objetivo
    return float(objetivo * base / ((1.0 - objetivo) * riesgo + 1e-18))


def peso_del_riesgo(banco_tr: dict, nombre: str, kw: dict) -> float:
    """Fracción del MOVIMIENTO de la señal que aporta el término de riesgo.

    Por ablación y no por álgebra, para que aplique a las seis por igual: se
    compara la recompensa contra su versión con el término de riesgo apagado.

    CORREGIDO EL 2026-09-19 — LA PRIMERA VERSIÓN NO MEDÍA ESTO. Comparaba
    |dsr − logret| / |dsr| con las dos series EN SUS UNIDADES CRUDAS, y el DSR
    vale ~1e0 por paso contra ~1e-3 del log-retorno: la razón daba 99% para
    cualquier recompensa de la familia diferencial, que es decir nada. Ahora
    CADA SERIE SE NORMALIZA por su propia magnitud media antes de restarlas, y
    lo que se mide es divergencia de FORMA, no de escala. Además se le pasa la
    rotación, sin la cual el castigo de `dsr_rot` era idénticamente cero y el
    brazo aparecía con 0% de término de riesgo.

    El umbral (20%) no se movió: era y sigue siendo el pre-registrado.
    """
    apagado = {
        "dsr": ("logret", {}), "ddr": ("logret", {}), "logret": ("logret", {}),
        "mv": ("logret", {}), "logret_dd": ("logret", {}), "dsr_rot": ("dsr", {}),
    }[nombre]
    masa_riesgo = masa_total = 0.0
    for v in banco_tr.values():
        r = v["retornos"]
        rot = v["rotacion"]
        if float(np.std(r)) * np.sqrt(DIAS) <= 1e-3:
            continue
        rec = make_reward(nombre, **kw)
        ref = make_reward(apagado[0], **apagado[1])
        rec.reset()
        ref.reset()
        a_s, b_s = [], []
        for x, t in zip(r, rot):
            a_s.append(rec.step(float(x), float(t)))
            b_s.append(ref.step(float(x), float(t)))
        a = np.asarray(a_s)
        b = np.asarray(b_s)
        ea = float(np.mean(np.abs(a))) + 1e-18
        eb = float(np.mean(np.abs(b))) + 1e-18
        masa_riesgo += float(np.sum(np.abs(a / ea - b / eb)))
        masa_total += float(np.sum(np.abs(a / ea)))
    return float(masa_riesgo / (masa_total + 1e-18))


def frontera_lambda(bancos: dict, forma: str, lam_ref: float) -> list[dict]:
    """Barre λ y mide el canje entre T1 (fidelidad de orden) y T3 (peso del riesgo).

    POR QUE HACE FALTA. λ no es un boton de desempeño: fija CUANTO pesa el
    riesgo frente al retorno. Subirlo mejora T3 y empeora T1, porque el
    acumulado se parece cada vez menos al retorno —que es contra lo que se mide
    el orden—. Hay entonces un λ MAXIMO compatible con ordenar bien, y un λ
    MINIMO compatible con que el riesgo pese. Si el intervalo es vacio, la
    forma funcional no sirve y no hay λ que la salve.

    SE MIDE SOBRE TRAIN Y VAL, NUNCA SOBRE UN AGENTE. Es calibracion por
    propiedad de la recompensa, no por resultado: la misma logica con que D22
    calibro la exploracion por rotacion.
    """
    out = []
    for mult in (0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0):
        lam = lam_ref * mult
        kw = {"lam": lam}
        fila = {"mult": mult, "lam": lam}
        for tramo, b in bancos.items():
            claves = [k for k in b
                      if float(np.std(b[k]["retornos"])) * np.sqrt(DIAS) > 1e-3]
            acum = np.array([acumula(b[k]["retornos"], forma, b[k]["rotacion"], **kw)
                             for k in claves])
            fila[f"rho_sharpe_{tramo}"] = spearman(
                acum, np.array([b[k]["sharpe_periodo"] for k in claves]))
            fila[f"rho_maxdd_{tramo}"] = spearman(
                acum, np.array([b[k]["max_drawdown"] for k in claves]))
        fila["peso_riesgo"] = peso_del_riesgo(bancos["train"], forma, kw)
        fila["PASA_T1"] = bool(fila["rho_sharpe_train"] >= UMBRAL_T1_RHO
                               and fila["rho_sharpe_val"] >= UMBRAL_T1_RHO)
        fila["PASA_T3"] = bool(fila["peso_riesgo"] >= UMBRAL_T3_PESO_RIESGO)
        out.append(fila)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fold", type=int, default=0)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--out", default=str(SALIDA))
    args = ap.parse_args()

    panel = load_panel(view="solo_mercado", warmup=WARMUP)
    costos = snapshot_cost_model(panel.tickers)
    primer_util = max(panel.features.warmup + 1, panel.first_tradable_index)
    p = walk_forward(panel.n_steps, n_folds=args.folds, start=primer_util)[args.fold]

    print("=" * 92)
    print(f"D4 — TAMIZ DE RECOMPENSAS  ·  pliegue {p.idx}  ·  sin entrenar, sin contador")
    print("=" * 92)

    bancos = {t: banco(panel, costos, p.rango(t)) for t in ("train", "val")}
    series_cal = [v["retornos"] for v in bancos["train"].values()
                  if float(np.std(v["retornos"])) * np.sqrt(DIAS) > 1e-3]

    lam_mv = calibra_escala(series_cal, "mv")
    lam_dd = calibra_escala(series_cal, "logret_dd")
    print(f"\nCALIBRACION POR ESCALA (regla de D4(a), 25% de la senial):")
    print(f"  mv         lam = {lam_mv:,.2f}")
    print(f"  logret_dd  lam = {lam_dd:,.2f}")
    print(f"  dsr_rot    kappa = 1.0 con escala local (ver docstring de DSRTurnover)")

    CANDIDATAS = {
        "dsr": {}, "ddr": {}, "logret": {},
        "mv": {"lam": lam_mv},
        "logret_dd": {"lam": lam_dd},
        "dsr_rot": {"kappa": 1.0},
    }

    res = {"fold": p.idx, "umbrales": {
        "T1_rho": UMBRAL_T1_RHO, "T3_peso_riesgo": UMBRAL_T3_PESO_RIESGO,
        "T4_caida_por_bp": UMBRAL_T4_CAIDA_POR_BP},
        "lambdas": {"mv": lam_mv, "logret_dd": lam_dd}, "resultados": {}}

    for nombre, kw in CANDIDATAS.items():
        fila: dict = {"kwargs": kw}

        # ---- T1: fidelidad de orden, en los dos tramos ----
        for tramo, b in bancos.items():
            claves = [k for k in b if float(np.std(b[k]["retornos"])) * np.sqrt(DIAS) > 1e-3]
            acum = np.array([acumula(b[k]["retornos"], nombre, b[k]["rotacion"], **kw)
                             for k in claves])
            sh = np.array([b[k]["sharpe_periodo"] for k in claves])
            ret = np.array([b[k]["retorno_total"] for k in claves])
            dd = np.array([b[k]["max_drawdown"] for k in claves])
            fila[f"rho_sharpe_{tramo}"] = spearman(acum, sh)
            fila[f"rho_retorno_{tramo}"] = spearman(acum, ret)
            fila[f"rho_drawdown_{tramo}"] = spearman(acum, dd)
            fila[f"n_estrategias_{tramo}"] = len(claves)

        # ---- T2: no paga por ruido ----
        # CORREGIDO EL 2026-09-19. La primera version reportaba el PEOR caso
        # relativo, (inf-base)/|base|, y con estrategias cuyo acumulado pasa
        # cerca de cero eso da cifras de tres digitos que no dicen nada del
        # signo. Lo que decide el criterio pre-registrado es SI SUBE, o sea el
        # SIGNO: se cuenta en que fraccion de las estrategias sube. El umbral
        # (ninguna) no se movio.
        sube = 0
        total = 0
        peor_rel = 0.0
        for b in bancos.values():
            for k, v in b.items():
                r = v["retornos"]
                if float(np.std(r)) * np.sqrt(DIAS) <= 1e-3:
                    continue
                m = float(np.mean(r))
                base = acumula(r, nombre, v["rotacion"], **kw)
                inf = acumula(m + 1.5 * (r - m), nombre, v["rotacion"], **kw)
                total += 1
                if inf > base:
                    sube += 1
                    peor_rel = max(peor_rel, (inf - base) / (abs(base) + 1e-12))
        fila["T2_frac_estrategias_que_suben"] = sube / max(total, 1)
        fila["T2_n_estrategias"] = total
        fila["T2_peor_ganancia_por_ruido"] = peor_rel

        # ---- T3: cuánto pesa el término de riesgo ----
        fila["T3_peso_riesgo"] = peso_del_riesgo(bancos["train"], nombre, kw)

        # ---- T4: ve el peaje ----
        b = bancos["val"]
        k0 = "1/N diario"
        r0, rot0 = b[k0]["retornos"], b[k0]["rotacion"]
        base = acumula(r0, nombre, rot0, **kw)
        caidas = [(base - acumula(r0 - c * 1e-4, nombre, rot0, **kw)) / (abs(base) + 1e-12)
                  for c in (1, 2, 5)]
        fila["T4_caida_por_bp"] = caidas[0]
        fila["T4_monotona"] = bool(caidas[0] <= caidas[1] <= caidas[2])

        fila["PASA_T1"] = bool(fila["rho_sharpe_train"] >= UMBRAL_T1_RHO
                               and fila["rho_sharpe_val"] >= UMBRAL_T1_RHO)
        fila["PASA_T2"] = bool(sube == 0)
        fila["PASA_T3"] = bool(fila["T3_peso_riesgo"] >= UMBRAL_T3_PESO_RIESGO)
        fila["PASA_T4"] = bool(caidas[0] >= UMBRAL_T4_CAIDA_POR_BP and fila["T4_monotona"])
        fila["PASA"] = all(fila[f"PASA_T{i}"] for i in (1, 2, 3, 4))
        res["resultados"][nombre] = fila

    # ------------------------------------------------------------------ tabla
    print(f"\n{'=' * 92}")
    print("T1 — FIDELIDAD DE ORDEN (rho de Spearman del acumulado contra...)")
    print("=" * 92)
    print(f"{'recompensa':<12} {'Sharpe tr':>10} {'Sharpe val':>11} {'ret tr':>8} "
          f"{'ret val':>8} {'maxDD tr':>9} {'maxDD val':>10}")
    for n, f in res["resultados"].items():
        print(f"{n:<12} {f['rho_sharpe_train']:>+10.2f} {f['rho_sharpe_val']:>+11.2f} "
              f"{f['rho_retorno_train']:>+8.2f} {f['rho_retorno_val']:>+8.2f} "
              f"{f['rho_drawdown_train']:>+9.2f} {f['rho_drawdown_val']:>+10.2f}")

    print(f"\n{'=' * 92}")
    print("VEREDICTO DEL TAMIZ")
    print("=" * 92)
    print(f"{'recompensa':<12} {'T1 orden':>9} {'T2 ruido':>9} {'T3 riesgo':>10} "
          f"{'T4 peaje':>9}   {'PASA':>5}")
    for n, f in res["resultados"].items():
        print(f"{n:<12} {'si' if f['PASA_T1'] else 'NO':>9} "
              f"{'si' if f['PASA_T2'] else 'NO':>9} "
              f"{'si' if f['PASA_T3'] else 'NO':>10} "
              f"{'si' if f['PASA_T4'] else 'NO':>9}   "
              f"{'SI' if f['PASA'] else 'no':>5}")
    print(f"\n{'recompensa':<12} {'estrategias donde el ruido PAGA':>33} "
          f"{'peso riesgo':>12} {'caida por bp':>13}")
    for n, f in res["resultados"].items():
        print(f"{n:<12} {f['T2_frac_estrategias_que_suben']:>26.0%} de "
              f"{f['T2_n_estrategias']:<3} {f['T3_peso_riesgo']:>12.1%} "
              f"{f['T4_caida_por_bp']:>13.2%}")

    # ------------------------------------------------- frontera T1 vs T3
    print(f"\n{'=' * 92}")
    print("FRONTERA T1-T3: hay un lambda que cumpla LAS DOS?")
    print("=" * 92)
    res["frontera"] = {}
    for forma, lam_ref in (("mv", lam_mv), ("logret_dd", lam_dd)):
        print(f"\n  {forma}   (lambda de referencia = {lam_ref:,.2f})")
        print(f"  {'mult':>6} {'lambda':>12} {'rho Sh tr':>10} {'rho Sh val':>11} "
              f"{'rho DD tr':>10} {'rho DD val':>11} {'peso riesgo':>12}   T1  T3")
        filas = frontera_lambda(bancos, forma, lam_ref)
        res["frontera"][forma] = filas
        for f in filas:
            print(f"  {f['mult']:>6.2f} {f['lam']:>12,.2f} "
                  f"{f['rho_sharpe_train']:>+10.2f} {f['rho_sharpe_val']:>+11.2f} "
                  f"{f['rho_maxdd_train']:>+10.2f} {f['rho_maxdd_val']:>+11.2f} "
                  f"{f['peso_riesgo']:>12.1%}   "
                  f"{'si' if f['PASA_T1'] else 'NO':>2}  {'si' if f['PASA_T3'] else 'NO':>2}")
        ok = [f for f in filas if f["PASA_T1"] and f["PASA_T3"]]
        print(f"  >> lambdas que cumplen LAS DOS: "
              f"{[round(f['lam'], 2) for f in ok] if ok else 'NINGUNO'}")

    salida = Path(args.out)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nartefacto: {salida}")


if __name__ == "__main__":
    main()
