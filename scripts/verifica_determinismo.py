# -*- coding: utf-8 -*-
"""¿Reproduce el agente con la misma semilla? (G.4 del insumo de redacción)

POR QUÉ EXISTE. El 11-oct DDPG NO reprodujo con la misma semilla una corrida del
09-oct (solo_mercado p0 s0: -11.0% vs -19.0%) con el mismo panel y la misma
configuración. Antes de relanzar la ablación R8 hay que saber si el
no-determinismo es real, a qué algoritmos afecta y si se corrige.

QUÉ HACE. Entrena la MISMA configuración con la MISMA semilla varias veces, cada
una en un PROCESO NUEVO (el 09 y el 11-oct fueron procesos distintos; repetir en
el mismo proceso no lo prueba), y compara:
  * la huella sha256 de los pesos finales de la política;
  * el desempeño de la política determinista sobre el tramo de TRAIN.
Se evalúa en TRAIN a propósito: no se mira validación, así que estas corridas no
son pruebas de estrategia y NO se anotan en el registro de D10.

`--concurrentes` lanza las repeticiones a la vez, como el 11-oct (DDPG y SAC en
paralelo): si el resultado depende de la carga de la CPU, aparece ahí.
`--hilos N` fija torch.set_num_threads(N) en cada hijo, para probar la hipótesis
de que el paralelismo de torch es la fuente.

Uso:
    python scripts/verifica_determinismo.py --algo ppo
    python scripts/verifica_determinismo.py --algo ddpg --ddpg-sigma 0.16
    python scripts/verifica_determinismo.py --algo ddpg --ddpg-sigma 0.16 --concurrentes
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
WARMUP = 250


def corre_una(args) -> dict:
    """Un entrenamiento completo; devuelve la huella. Corre en el proceso HIJO."""
    import numpy as np
    import torch

    if args.hilos:
        torch.set_num_threads(args.hilos)

    sys.path.insert(0, str(RAIZ))
    sys.path.insert(0, str(RAIZ / "scripts"))
    from stable_baselines3.common.env_util import make_vec_env

    from src.agents import construye_modelo, envuelve, exploracion
    from src.env import load_panel, costos_observados
    from src.env.folds import walk_forward
    from train_ppo_oe1 import construye_env, evalua

    explora = exploracion(args.algo, log_std=args.log_std,
                          ent_coef=args.sac_ent_coef, sigma=args.ddpg_sigma)
    # Lo MISMO que ablacion_r8.py: si esto difiriera, el chequeo no diría nada
    # sobre la ablación.
    cfg_extra = {"reward": "dsr", "reward_kwargs": {}, "rebalance_every": 1,
                 "action_mode": "delta", "action_scale": 0.05}
    n_envs = 4 if args.algo == "ppo" else 1

    panel = load_panel(view=args.view, warmup=WARMUP)
    costos = costos_observados(panel)
    primer_util = max(panel.features.warmup + 1, panel.first_tradable_index)
    p = walk_forward(panel.n_steps, n_folds=3, start=primer_util)[args.fold]

    entorno = make_vec_env(
        lambda: envuelve(construye_env(panel, costos, p.rango("train"), entrenando=True,
                                       cfg_extra=cfg_extra), args.algo),
        n_envs=n_envs,
        seed=args.seed,
    )
    modelo = construye_modelo(args.algo, entorno, semilla=args.seed,
                              explora=explora, timesteps=args.timesteps)
    t0 = time.time()
    modelo.learn(total_timesteps=args.timesteps, progress_bar=False)
    seg = time.time() - t0

    h = hashlib.sha256()
    for nombre, tensor in sorted(modelo.policy.state_dict().items()):
        h.update(nombre.encode())
        h.update(tensor.detach().cpu().numpy().tobytes())
    s = evalua(modelo, panel, costos, p.rango("train"), cfg_extra, algo=args.algo)
    return {
        "pesos_sha": h.hexdigest()[:16],
        "retorno_train": s["retorno_total"],
        "sharpe_train": s["sharpe"],
        "segundos": round(seg, 1),
        "hilos_torch": torch.get_num_threads(),
        "np": np.__version__,
        "torch": torch.__version__,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--algo", default="ppo", choices=["ppo", "sac", "ddpg"])
    ap.add_argument("--log-std", type=float, default=-2.0)
    ap.add_argument("--sac-ent-coef", type=float, default=None)
    ap.add_argument("--ddpg-sigma", type=float, default=None)
    ap.add_argument("--view", default="solo_mercado")
    ap.add_argument("--fold", type=int, default=0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--timesteps", type=int, default=5_000)
    ap.add_argument("--repeticiones", type=int, default=2)
    ap.add_argument("--concurrentes", action="store_true",
                    help="lanzar las repeticiones a la vez (como el 11-oct)")
    ap.add_argument("--hilos", type=int, default=None, help="torch.set_num_threads en cada hijo")
    ap.add_argument("--hijo", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.hijo:
        print(json.dumps(corre_una(args)))
        return

    hijo = [sys.executable, "-X", "utf8", __file__, "--hijo"] + [
        a for a in sys.argv[1:] if a != "--concurrentes"
    ]
    print(f"{args.algo.upper()} · {args.view} p{args.fold} s{args.seed} · {args.timesteps:,} pasos · "
          f"{args.repeticiones} procesos {'A LA VEZ' if args.concurrentes else 'en serie'}"
          + (f" · hilos={args.hilos}" if args.hilos else ""))
    if args.concurrentes:
        procs = [subprocess.Popen(hijo, stdout=subprocess.PIPE, text=True, cwd=RAIZ)
                 for _ in range(args.repeticiones)]
        salidas = [p.communicate()[0] for p in procs]
    else:
        salidas = [subprocess.run(hijo, stdout=subprocess.PIPE, text=True, cwd=RAIZ, check=True).stdout
                   for _ in range(args.repeticiones)]
    res = [json.loads(s.strip().splitlines()[-1]) for s in salidas]
    for i, r in enumerate(res):
        print(f"  #{i}: pesos {r['pesos_sha']}  ret_train {r['retorno_train']:+.6%}  "
              f"sharpe {r['sharpe_train']:+.6f}  ({r['segundos']} s, {r['hilos_torch']} hilos)")
    iguales = len({r["pesos_sha"] for r in res}) == 1
    print("DETERMINISTA: pesos idénticos en todas las repeticiones" if iguales
          else "NO DETERMINISTA: los pesos difieren con la misma semilla")
    sys.exit(0 if iguales else 1)


if __name__ == "__main__":
    main()
