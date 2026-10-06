# -*- coding: utf-8 -*-
"""D25 — ¿cuánto entrenamiento hace falta? Y de paso: ¿sobreajusta al entrenar más?

DOS PREGUNTAS DISTINTAS QUE NO HAY QUE MEZCLAR, y la distinción ES la decisión:

  (1) ¿DÓNDE HACE MESETA LA CURVA DE ENTRENAMIENTO? Es un criterio de
      COMPORTAMIENTO, medido sobre `train`. **Es el único que puede elegir el
      presupuesto**, porque no mira el resultado en validación. Así lo fija D25,
      por la misma lógica de D22 (la escala de exploración se calibró por
      rotación, no por Sharpe).

  (2) ¿EMPEORA LA VALIDACIÓN AL ENTRENAR MÁS? Es DESCRIPTIVO. Contesta si hay
      sobreajuste al régimen de entrenamiento —que en el pliegue 0 es el opuesto
      al de validación (§7.4)— y es información valiosa para la tesis.
      >> PERO NO PUEDE ELEGIR EL PRESUPUESTO. Tomar el checkpoint que mejor
         valida es selección encubierta: sería entrenar 4 configuraciones y
         quedarse con la mejor sin pagarlo en el contador de D10.
      Se mide, se reporta, y la decisión NO lo usa. Está escrito acá para que
      no se preste a confusión después.

LA TERCERA PREGUNTA, que es la que de verdad importa para el rendimiento: la
DISPERSIÓN ENTRE SEMILLAS. Hoy una celda de la ablación va de -2% a +23%. Si esa
dispersión CAE con el presupuesto, es ruido de entrenamiento y más pasos
mejoran al agente mediano. Si NO cae, es multimodalidad genuina —la política se
asienta en "me quedo afuera" o en "entro"— y el presupuesto no la arregla: hay
que atacarla por otro lado. Las dos respuestas son publicables y cambian qué se
hace después.

Uso:
    python scripts/d25_presupuesto.py                      # 3 semillas, 1M pasos
    python scripts/d25_presupuesto.py --seeds 5 --timesteps 2000000
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

from src.env import load_panel, snapshot_cost_model  # noqa: E402
from src.env.folds import walk_forward  # noqa: E402
from src.env.registro import conteo, registra  # noqa: E402
from train_ppo_oe1 import construye_env, evalua  # noqa: E402

SALIDA = Path("data/interim/artefactos_oe1/d25_presupuesto.json")
CURVAS = Path("data/interim/artefactos_oe1/d25_curvas.npz")
WARMUP = 250


def callback_curva():
    """Igual que el de genera_artefactos_oe1: recompensa POR PASO, que es la
    única comparable cuando `random_start` hace los episodios de largo variable."""
    from stable_baselines3.common.callbacks import BaseCallback

    class Curva(BaseCallback):
        def __init__(self) -> None:
            super().__init__()
            self.pasos: list[int] = []
            self.recompensa_paso: list[float] = []
            self.largo_ep: list[float] = []

        def _on_step(self) -> bool:
            return True

        def _on_rollout_end(self) -> None:
            buf = [e for e in (self.model.ep_info_buffer or []) if e.get("l", 0) > 0]
            if not buf:
                return
            r = np.array([e["r"] for e in buf], dtype=float)
            ln = np.array([e["l"] for e in buf], dtype=float)
            self.pasos.append(int(self.num_timesteps))
            self.recompensa_paso.append(float((r / ln).mean()))
            self.largo_ep.append(float(ln.mean()))

    return Curva()


def meseta(pasos: np.ndarray, valores: np.ndarray, ventanas: int = 10) -> dict:
    """¿Dónde deja de subir la curva? Criterio explícito y reproducible.

    Se parte la curva en `ventanas` tramos iguales por PASOS y se compara la
    media de cada tramo con la del anterior. La meseta es el primer tramo a
    partir del cual ninguna mejora posterior supera el RUIDO de la propia curva
    (desviación estándar de las diferencias entre tramos). No es un umbral
    elegido a mano: la escala la pone la curva.
    """
    if len(pasos) < ventanas * 2:
        return {"meseta_en": None, "motivo": "curva demasiado corta"}
    bordes = np.linspace(pasos[0], pasos[-1], ventanas + 1)
    medias, centros = [], []
    for a, b in zip(bordes[:-1], bordes[1:]):
        m = (pasos >= a) & (pasos <= b)
        if m.sum():
            medias.append(float(np.mean(valores[m])))
            centros.append(float(np.mean(pasos[m])))
    medias = np.array(medias)
    difs = np.diff(medias)
    ruido = float(np.std(difs))
    for i in range(len(difs)):
        if np.all(difs[i:] <= ruido):
            return {
                "meseta_en": int(centros[i]),
                "ruido_entre_tramos": ruido,
                "medias_por_tramo": medias.tolist(),
                "centros": centros,
            }
    return {
        "meseta_en": None,
        "motivo": "sigue subiendo al final del presupuesto",
        "ruido_entre_tramos": ruido,
        "medias_por_tramo": medias.tolist(),
        "centros": centros,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--view", default="solo_mercado")
    ap.add_argument("--fold", type=int, default=0)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--timesteps", type=int, default=1_000_000)
    ap.add_argument("--checkpoints", type=int, nargs="+",
                    default=[150_000, 300_000, 600_000, 1_000_000])
    ap.add_argument("--reward", default="dsr")
    ap.add_argument("--log-std", type=float, default=-2.0)
    ap.add_argument("--n-envs", type=int, default=4)
    args = ap.parse_args()

    from stable_baselines3 import PPO
    from stable_baselines3.common.env_util import make_vec_env

    t0 = time.time()
    checkpoints = sorted(c for c in args.checkpoints if c <= args.timesteps)
    print("=" * 84)
    print("D25 — PRESUPUESTO DE PASOS")
    print("=" * 84)
    print(f"vista {args.view} · pliegue {args.fold} · {args.seeds} semillas · "
          f"{args.timesteps:,} pasos")
    print(f"checkpoints: {', '.join(f'{c:,}' for c in checkpoints)}")
    print("La MESETA decide el presupuesto. La validación se mide pero NO decide.\n")

    panel = load_panel(view=args.view, warmup=WARMUP)
    costos = snapshot_cost_model(panel.tickers)
    primer_util = max(panel.features.warmup + 1, panel.first_tradable_index)
    pliegues = walk_forward(panel.n_steps, n_folds=args.folds, start=primer_util)
    p = pliegues[args.fold]
    print(p.describe(panel.dates), "\n")

    cfg_extra = {"reward": args.reward, "rebalance_every": 1,
                 "action_mode": "delta", "action_scale": 0.05}
    out: dict = {"config": vars(args), "semillas": {}}
    curvas_npz: dict[str, np.ndarray] = {}

    for semilla in range(args.seeds):
        entorno = make_vec_env(
            lambda: construye_env(panel, costos, p.rango("train"),
                                  entrenando=True, cfg_extra=cfg_extra),
            n_envs=args.n_envs,
            seed=semilla,
        )
        modelo = PPO(
            "MlpPolicy", entorno, seed=semilla, verbose=0,
            n_steps=512, batch_size=256, gamma=0.99, ent_coef=0.0,
            policy_kwargs={"net_arch": [64, 64], "log_std_init": args.log_std},
        )
        cb = callback_curva()
        hechos, evals = 0, []
        for objetivo in checkpoints:
            faltan = objetivo - hechos
            if faltan <= 0:
                continue
            modelo.learn(total_timesteps=faltan, callback=cb,
                         reset_num_timesteps=False, progress_bar=False)
            hechos = objetivo
            s = evalua(modelo, panel, costos, p.rango("val"), cfg_extra)
            s["pasos"] = objetivo
            evals.append(s)
            registra(
                {"view": args.view, "reward": args.reward, "rebalance_every": 1,
                 "fold": args.fold, "action_mode": "delta", "action_scale": 0.05,
                 "log_std_init": args.log_std, "timesteps": objetivo,
                 "algoritmo": "PPO", "net_arch": [64, 64], "seed": semilla,
                 "estudio": "D25"},
                tramo="val", resultado=s,
            )
            print(f"  s{semilla} @ {objetivo:>9,}: ret {s['retorno_total']:+7.1%} "
                  f"sharpe {s['sharpe']:6.2f} maxDD {s['max_drawdown']:+6.1%} "
                  f"rot {s['rotacion_anual']:5.2f} caja {s['peso_caja_medio']:5.1%}"
                  f"   [{(time.time()-t0)/60:.0f} min]")

        pasos = np.asarray(cb.pasos, dtype=float)
        rp = np.asarray(cb.recompensa_paso, dtype=float)
        out["semillas"][str(semilla)] = {
            "checkpoints": evals,
            "meseta": meseta(pasos, rp),
        }
        curvas_npz[f"s{semilla}__pasos"] = pasos
        curvas_npz[f"s{semilla}__recompensa_paso"] = rp
        curvas_npz[f"s{semilla}__largo_ep"] = np.asarray(cb.largo_ep, dtype=float)
        m = out["semillas"][str(semilla)]["meseta"]
        print(f"  s{semilla} meseta: "
              + (f"{m['meseta_en']:,} pasos" if m.get("meseta_en") else f"NO alcanzada ({m.get('motivo')})"))

        SALIDA.parent.mkdir(parents=True, exist_ok=True)
        SALIDA.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        np.savez_compressed(CURVAS, **curvas_npz)

    # ------------------------------------------------------------------ lectura
    print(f"\n{'=' * 84}\n(1) MESETA — el criterio QUE SÍ decide\n{'=' * 84}")
    for s, d in out["semillas"].items():
        m = d["meseta"]
        print(f"  semilla {s}: " + (f"meseta en ~{m['meseta_en']:,} pasos"
                                    if m.get("meseta_en") else f"NO alcanzada — {m.get('motivo')}"))

    print(f"\n{'=' * 84}\n(2) VALIDACIÓN POR CHECKPOINT — descriptivo, NO decide\n{'=' * 84}")
    print(f"  {'pasos':>10}{'ret med':>10}{'ret p25':>10}{'ret p75':>10}"
          f"{'RANGO':>9}{'sharpe':>9}{'maxDD':>9}{'caja':>8}")
    for c in checkpoints:
        rr = [e for s in out["semillas"].values() for e in s["checkpoints"] if e["pasos"] == c]
        if not rr:
            continue
        r = [x["retorno_total"] for x in rr]
        print(f"  {c:>10,}{np.median(r):>+10.1%}{np.percentile(r,25):>+10.1%}"
              f"{np.percentile(r,75):>+10.1%}{max(r)-min(r):>9.1%}"
              f"{np.median([x['sharpe'] for x in rr]):>9.2f}"
              f"{np.median([x['max_drawdown'] for x in rr]):>+9.1%}"
              f"{np.median([x['peso_caja_medio'] for x in rr]):>8.1%}")

    print(f"\n{'=' * 84}\n(3) ¿CAE LA DISPERSIÓN ENTRE SEMILLAS? — la pregunta que importa\n{'=' * 84}")
    print("  Si el rango se ACHICA con los pasos, era ruido de entrenamiento y más")
    print("  presupuesto mejora al agente mediano. Si NO se achica, es multimodalidad")
    print("  (la política se asienta en 'afuera' o en 'adentro') y el presupuesto no")
    print("  la arregla: hay que atacarla por otro lado.\n")
    rangos = []
    for c in checkpoints:
        r = [e["retorno_total"] for s in out["semillas"].values()
             for e in s["checkpoints"] if e["pasos"] == c]
        if r:
            rangos.append((c, max(r) - min(r), float(np.std(r))))
    for c, rango, sd in rangos:
        print(f"  {c:>10,} pasos: rango {rango:6.1%}   desv. estándar {sd:6.1%}")
    if len(rangos) >= 2:
        print(f"\n  del primer al último checkpoint el rango pasa de "
              f"{rangos[0][1]:.1%} a {rangos[-1][1]:.1%} "
              f"({'CAE' if rangos[-1][1] < rangos[0][1] else 'NO CAE'}).")

    print(f"\nregistro (D10): {conteo()}")
    print(f"artefactos: {SALIDA} · {CURVAS}")
    print(f"\nterminado en {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
