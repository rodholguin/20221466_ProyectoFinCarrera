# -*- coding: utf-8 -*-
"""R8 — ablación de canales de señal: ¿aporta cada canal, y cuánto?

QUÉ CONTESTA. El documento de tesis (R8) compromete comparar el agente "bajo
cuatro configuraciones de señales de entrada". Acá se corre esa comparación:

    solo_mercado           base
    mercado_macro          base + cobre, EMBI, tasa, inflación, TC, SPX, MSCI-EM
    mercado_sentimiento    base + las 9 columnas categóricas de D15 + 4 de volumen
    mercado_fundamentales  base + niveles, P/E, DY y las 13 de forma del acta §B3

CADA BRAZO AÑADE UN SOLO CANAL sobre la MISMA base. Hasta el 2026-09-12 no era
así —macro venía escondido dentro de dos de las vistas— y la ablación habría
sido inatribuible. Hay una guarda en tests/test_vistas_r8.py.

POR QUÉ LAS SEMILLAS VAN EMPAREJADAS. La semilla k de `mercado_macro` se compara
contra la semilla k de `solo_mercado`: mismo sorteo de arranques, misma
inicialización. La diferencia PAREADA cancela buena parte de la varianza entre
semillas, que en la sección 7.4(d) de resultados resultó ser grande. Comparar
medianas sueltas desperdicia esa estructura.

POR QUÉ TRES PLIEGUES Y NO UNO. Está medido que la validación del pliegue 0 fue
el mejor año de la década (+11.9% el 1/N) y las de los pliegues 1 y 2 fueron
años de caída (-8%). Un solo pliegue mide el RÉGIMEN, no el canal.

LO QUE ESTO **NO** ES:
  * No es la corrida definitiva. Son 3 semillas; D10 pide 10 antes de reportar
    cualquier cosa como resultado.
  * NO TOCA EL TRAMO DE PRUEBA. Todo se evalúa sobre `val` y se anota con
    tramo='val' en el registro de D10.
  * Hereda D25: las curvas no llegan a meseta al presupuesto actual de pasos,
    así que esto compara agentes SUBENTRENADOS. Es comparable entre brazos
    (todos reciben el mismo presupuesto) pero no es el techo de ninguno.

COSTO EN EL CONTADOR DE D10, y hay que decirlo en voz alta: 4 vistas x 3
pliegues son 12 configuraciones distintas, de las cuales 11 son nuevas. Eso
degrada el Sharpe deflactado de la evaluación final. Es el precio de R8 y está
pre-registrado en el propio documento de tesis, no es una pesca.

Uso:
    python scripts/ablacion_r8.py                       # 4 vistas x 3 pliegues x 3 semillas
    python scripts/ablacion_r8.py --seeds 10 --folds 3  # la corrida en serio
    python scripts/ablacion_r8.py --views solo_mercado mercado_fundamentales
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

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
from src.env.features import VISTAS_ABLACION  # noqa: E402
from src.env.folds import walk_forward  # noqa: E402
from src.env.registro import conteo, registra  # noqa: E402

# Se IMPORTAN del piloto en vez de copiarse. Si el entorno de evaluación de la
# ablación se construyera distinto del entorno del piloto, los números no serían
# comparables y nadie se daría cuenta — es exactamente la deriva que este
# proyecto ya sufrió tres veces.
from train_ppo_oe1 import construye_env, evalua  # noqa: E402

SALIDA = Path("data/interim/artefactos_oe1/ablacion_r8.json")
WARMUP = 250

METRICAS = [
    ("retorno_total", "{:+7.1%}"),
    ("retorno_anualizado", "{:+7.1%}"),
    ("sharpe", "{:7.2f}"),
    ("sortino", "{:7.2f}"),
    ("max_drawdown", "{:+7.1%}"),
    ("rotacion_anual", "{:7.2f}"),
    ("peso_caja_medio", "{:7.1%}"),
]


def baselines_del_tramo(panel, costos, rango) -> dict:
    """Las referencias sobre el MISMO tramo, dentro del MISMO simulador."""
    out = {}
    for etiqueta, pol, freq in [
        ("1/N diario", EqualWeight(), 1),
        ("1/N mensual", EqualWeight(), 21),
        ("solo caja", CashOnly(), 1),
        ("markowitz", Markowitz(window=252, min_obs=60), 21),
    ]:
        env = PortfolioEnv(
            panel,
            costos,
            EnvConfig(
                action_mode="weights",
                rebalance_every=freq,
                start_index=rango[0],
                end_index=rango[1],
            ),
        )
        s = run_policy(env, pol)["summary"]
        s["peso_caja_medio"] = 0.0 if etiqueta != "solo caja" else 1.0
        out[etiqueta] = s
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--views", nargs="+", default=list(VISTAS_ABLACION))
    # 150k es el presupuesto del piloto A PROPÓSITO: con él, el brazo
    # `solo_mercado` del pliegue 0 tiene que REPRODUCIR las corridas que ya
    # están en el registro (la winsorización de D27 no toca ese brazo, no tiene
    # columnas sue_). Es una verificación gratis de que nada más se movió.
    ap.add_argument("--timesteps", type=int, default=150_000)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--reward", default="dsr", choices=["dsr", "ddr", "logret"])
    ap.add_argument("--log-std", type=float, default=-2.0)
    ap.add_argument("--action-mode", default="delta", choices=["delta", "logits"])
    ap.add_argument("--action-scale", type=float, default=0.05)
    ap.add_argument("--rebalance-every", type=int, default=1)
    ap.add_argument("--n-envs", type=int, default=4)
    args = ap.parse_args()

    from stable_baselines3 import PPO
    from stable_baselines3.common.env_util import make_vec_env

    t0 = time.time()
    print("=" * 84)
    print("R8 — ABLACIÓN DE CANALES")
    print("=" * 84)
    print(f"vistas   : {', '.join(args.views)}")
    print(f"pliegues : {args.folds}  ·  semillas: {args.seeds}  ·  pasos: {args.timesteps:,}")
    print(f"total    : {len(args.views) * args.folds * args.seeds} corridas")
    print("EL TRAMO DE PRUEBA NO SE TOCA: todo se evalúa sobre val (D21).\n")

    cfg_extra = {
        "reward": args.reward,
        "rebalance_every": args.rebalance_every,
        "action_mode": args.action_mode,
        "action_scale": args.action_scale,
    }

    resultados: dict = {"config": vars(args), "vistas": {}, "baselines": {}, "dims": {}}

    # Los pliegues se calculan una sola vez, con la vista base: la partición
    # depende del CALENDARIO, no de cuántas columnas tenga la observación.
    panel_base = load_panel(view=args.views[0], warmup=WARMUP)
    primer_util = max(panel_base.features.warmup + 1, panel_base.first_tradable_index)
    pliegues = walk_forward(panel_base.n_steps, n_folds=args.folds, start=primer_util)

    for vista in args.views:
        panel = load_panel(view=vista, warmup=WARMUP)
        dim = panel.features.flat_dim() + panel.n_assets + 1 + 2
        resultados["dims"][vista] = {
            "columnas_por_activo": len(panel.features.columns),
            "dim_observacion": dim,
        }
        costos = snapshot_cost_model(panel.tickers)
        print(f"\n{'=' * 84}\n{vista}  ({len(panel.features.columns)} cols/activo · obs {dim})\n{'=' * 84}")
        resultados["vistas"][vista] = {}

        for p in pliegues:
            if vista == args.views[0]:
                resultados["baselines"][f"pliegue{p.idx}"] = baselines_del_tramo(
                    panel, costos, p.rango("val")
                )
            base_cfg = {
                "view": vista,
                "reward": args.reward,
                "rebalance_every": args.rebalance_every,
                "fold": p.idx,
                "action_mode": args.action_mode,
                "action_scale": args.action_scale,
                "log_std_init": args.log_std,
                "timesteps": args.timesteps,
                "algoritmo": "PPO",
                "net_arch": [64, 64],
            }
            por_semilla = []
            for semilla in range(args.seeds):
                entorno = make_vec_env(
                    lambda: construye_env(
                        panel, costos, p.rango("train"), entrenando=True, cfg_extra=cfg_extra
                    ),
                    n_envs=args.n_envs,
                    seed=semilla,
                )
                modelo = PPO(
                    "MlpPolicy",
                    entorno,
                    seed=semilla,
                    verbose=0,
                    n_steps=512,
                    batch_size=256,
                    gamma=0.99,
                    ent_coef=0.0,
                    policy_kwargs={"net_arch": [64, 64], "log_std_init": args.log_std},
                )
                modelo.learn(total_timesteps=args.timesteps, progress_bar=False)
                s = evalua(modelo, panel, costos, p.rango("val"), cfg_extra)
                s["seed"] = semilla
                por_semilla.append(s)
                # D10: se anota ANTES de mirar si el resultado gusta.
                registra({**base_cfg, "seed": semilla}, tramo="val", resultado=s)
                print(
                    f"  pliegue{p.idx} s{semilla}: ret {s['retorno_total']:+7.1%} "
                    f"sharpe {s['sharpe']:6.2f} sortino {s['sortino']:6.2f} "
                    f"maxDD {s['max_drawdown']:+6.1%} rot {s['rotacion_anual']:5.2f} "
                    f"caja {s['peso_caja_medio']:5.1%}  [{(time.time()-t0)/60:.0f} min]"
                )
            resultados["vistas"][vista][f"pliegue{p.idx}"] = por_semilla

        SALIDA.parent.mkdir(parents=True, exist_ok=True)
        SALIDA.write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------------ tablas
    def med(vista: str, fold: int, clave: str) -> float:
        return float(np.median([r[clave] for r in resultados["vistas"][vista][f"pliegue{fold}"]]))

    print(f"\n\n{'=' * 84}\nRESULTADO — mediana de {args.seeds} semillas, sobre VALIDACIÓN\n{'=' * 84}")
    for p in pliegues:
        fechas = p.fechas(panel_base.dates, "val")
        print(f"\npliegue {p.idx} · val {fechas[0]} .. {fechas[1]}")
        print(f"  {'brazo':<26}" + "".join(f"{k.split('_')[0][:8]:>9}" for k, _ in METRICAS))
        for vista in args.views:
            fila = "".join(f.format(med(vista, p.idx, k)) + "  " for k, f in METRICAS)
            print(f"  {vista:<26}{fila}")
        for etiqueta, s in resultados["baselines"][f"pliegue{p.idx}"].items():
            fila = "".join(f.format(s.get(k, 0.0)) + "  " for k, f in METRICAS)
            print(f"  {'· ' + etiqueta:<26}{fila}")

    print(f"\n\n{'=' * 84}\nAPORTE DE CADA CANAL — diferencia PAREADA por semilla contra solo_mercado")
    print("=" * 84)
    print("Cada celda es mediana_semillas(brazo_k - solo_mercado_k). Positivo = el canal aporta.")
    base_v = "solo_mercado"
    if base_v in args.views:
        for clave in ("retorno_total", "sharpe", "sortino", "max_drawdown"):
            print(f"\n  {clave}")
            print(f"    {'brazo':<26}" + "".join(f"{'pliegue' + str(p.idx):>12}" for p in pliegues)
                  + f"{'los tres':>12}")
            for vista in args.views:
                if vista == base_v:
                    continue
                celdas, todo = [], []
                for p in pliegues:
                    a = resultados["vistas"][vista][f"pliegue{p.idx}"]
                    b = resultados["vistas"][base_v][f"pliegue{p.idx}"]
                    d = [x[clave] - y[clave] for x, y in zip(a, b)]
                    todo += d
                    celdas.append(f"{np.median(d):>+12.3f}")
                print(f"    {vista:<26}" + "".join(celdas) + f"{np.median(todo):>+12.3f}")

    print(f"\n\nregistro de configuraciones (D10): {conteo()}")
    print(f"artefacto: {SALIDA}")
    print(f"\nterminado en {(time.time()-t0)/60:.1f} min")
    print(
        "\nRECORDATORIO: 3 semillas es DIAGNÓSTICO, no resultado. D10 pide 10 "
        "semillas y pre-registro antes de reportar nada como hallazgo, y D25 "
        "sigue abierta: estos agentes están subentrenados por igual."
    )


if __name__ == "__main__":
    main()
