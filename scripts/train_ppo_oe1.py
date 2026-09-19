# -*- coding: utf-8 -*-
"""MVP de OE1 — entrena PPO en el entorno de portafolio y lo diagnostica.

REGLA DE D21, y es la razón de ser de este script tal como está escrito:
**EL TRAMO DE PRUEBA NO SE TOCA.** Se entrena en `train` y se diagnostica en
`val`. El `test` de cada pliegue se calcula solo para EXCLUIRLO explícitamente y
para que quede registrado que existe. Si se usa el piloto para tomar decisiones
de diseño y esas decisiones se validan sobre el test, el argumento del Sharpe
deflactado se cae. Por eso también cada corrida se anota en el registro de
configuraciones desde la primera vez (D10).

Uso:
    python scripts/train_ppo_oe1.py                       # MVP: 3 semillas, pliegue 0
    python scripts/train_ppo_oe1.py --timesteps 400000 --seeds 5
    python scripts/train_ppo_oe1.py --view mercado_macro --reward ddr

Notas de implementación que NO son cosméticas:
  * NO se usa VecNormalize. Normalizar observaciones con estadísticas del
    rollout mezclaría episodios y ventanas, y rompería la causalidad que D6
    garantiza. Las features ya llegan normalizadas y causales del panel.
  * La red es chica (64x64) a propósito: ~3,300 días de una sola trayectoria
    histórica. La nota de riesgo del registro pide arquitecturas simples y
    desconfiar de cualquier resultado que dependa de una sola corrida.
  * El entrenamiento sortea el día de arranque (`random_start`); la evaluación
    NO, porque ahí el episodio tiene que ser el tramo completo.
  * La escala de exploración (`--log-std`) NO usa el defecto de SB3. Con
    log_std_init=0 sobre un espacio de acción de símplex, el ruido gaussiano
    re-sortea la asignación entera en cada paso: la política estocástica rota
    206 veces al año y paga un peaje que NO produce su acción media, así que el
    gradiente no puede aprender a evitarlo. Ver D22 en el registro.
"""
from __future__ import annotations

import argparse
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
from src.env.registro import conteo, registra  # noqa: E402


def construye_env(panel, costos, rango, *, entrenando: bool, cfg_extra: dict):
    a, b = rango
    return PortfolioEnv(
        panel,
        costos,
        EnvConfig(
            start_index=a,
            end_index=b,
            random_start=entrenando,
            **cfg_extra,
        ),
    )


def evalua(model, panel, costos, rango, cfg_extra: dict) -> dict:
    """Corre la política determinista sobre el tramo completo."""
    env = construye_env(panel, costos, rango, entrenando=False, cfg_extra=cfg_extra)
    obs, _ = env.reset()
    done = False
    while not done:
        accion, _ = model.predict(obs, deterministic=True)
        obs, _, terminado, truncado, _ = env.step(accion)
        done = terminado or truncado
    resumen = env.summary()
    resumen["peso_caja_medio"] = float(np.mean([w[-1] for w in env.history["weights"]]))
    return resumen


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--view", default="solo_mercado", help="vista de señales (R8)")
    ap.add_argument("--reward", default="dsr", choices=["dsr", "ddr", "logret"])
    ap.add_argument("--timesteps", type=int, default=200_000)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--fold", type=int, default=0)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--rebalance-every", type=int, default=1)
    ap.add_argument("--n-envs", type=int, default=4)
    # Ver D22: la escala de exploración se calibra por ROTACIÓN, no por
    # desempeño. Con el defecto de SB3 (log_std_init=0) la política estocástica
    # rota 206 veces al año y el costo del ruido tapa por completo la señal.
    ap.add_argument("--log-std", type=float, default=-2.0)
    ap.add_argument("--action-mode", default="delta", choices=["delta", "logits"],
                    help="delta = ajuste sobre los pesos actuales (D2 enmendada)")
    ap.add_argument("--action-scale", type=float, default=0.05)
    ap.add_argument("--ent-coef", type=float, default=0.0)
    args = ap.parse_args()

    from stable_baselines3 import PPO  # import tardío: el script sirve de doc sin SB3
    from stable_baselines3.common.env_util import make_vec_env

    panel = load_panel(view=args.view, warmup=250)
    costos = snapshot_cost_model(panel.tickers)
    # El primer índice utilizable no es 0: hay que esperar el calentamiento de
    # D6 y que los 7 activos coticen (InRetail sale a bolsa en 2012-10).
    primer_util = max(panel.features.warmup + 1, panel.first_tradable_index)
    pliegues = walk_forward(panel.n_steps, n_folds=args.folds, start=primer_util)
    for p in pliegues:
        print(p.describe(panel.dates))
    pliegue = pliegues[args.fold]
    print(f"\n>> se usa el {pliegue.describe(panel.dates)}")
    print(">> el tramo de PRUEBA no se toca en este piloto (D21)\n")

    cfg_extra = {
        "reward": args.reward,
        "rebalance_every": args.rebalance_every,
        "action_mode": args.action_mode,
        "action_scale": args.action_scale,
    }
    base_cfg = {
        "view": args.view,
        "reward": args.reward,
        "rebalance_every": args.rebalance_every,
        "fold": args.fold,
        "action_mode": args.action_mode,
        "action_scale": args.action_scale,
        "log_std_init": args.log_std,
        "timesteps": args.timesteps,
        "algoritmo": "PPO",
        "net_arch": [64, 64],
    }

    # --- referencia: los baselines sobre el MISMO tramo de validación ---
    print("baselines sobre validación:")
    referencias = {}
    for etiqueta, pol, freq in [
        ("1/N diario", EqualWeight(), 1),
        ("1/N mensual", EqualWeight(), 21),
        ("solo caja", CashOnly(), 1),
        # D26 — media-varianza clásica, mensual por el requisito de equidad de
        # frecuencias de D10. Es el tercer baseline que compromete el documento
        # (§2.2.4) y sin él la tabla de R8 no se acredita.
        ("markowitz", Markowitz(window=252, min_obs=60), 21),
    ]:
        env = PortfolioEnv(
            panel,
            costos,
            EnvConfig(
                start_index=pliegue.val[0],
                end_index=pliegue.val[1],
                action_mode="weights",
                rebalance_every=freq,
                reward=args.reward,
            ),
        )
        s = run_policy(env, pol)["summary"]
        referencias[etiqueta] = s
        print(
            f"  {etiqueta:12s} ret {s['retorno_total']:7.1%} | sharpe {s['sharpe']:6.2f} "
            f"| sortino {s['sortino']:6.2f} | maxDD {s['max_drawdown']:6.1%} "
            f"| rot {s['rotacion_anual']:5.2f}"
        )

    # --- agente ---
    print(f"\nentrenando PPO · {args.seeds} semillas · {args.timesteps:,} pasos c/u")
    resultados = []
    for semilla in range(args.seeds):
        entorno = make_vec_env(
            lambda: construye_env(panel, costos, pliegue.train, entrenando=True, cfg_extra=cfg_extra),
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
            ent_coef=args.ent_coef,
            policy_kwargs={"net_arch": [64, 64], "log_std_init": args.log_std},
        )
        modelo.learn(total_timesteps=args.timesteps, progress_bar=False)

        s = evalua(modelo, panel, costos, pliegue.val, cfg_extra)
        resultados.append(s)
        # D10: se anota ANTES de mirar si el resultado gusta.
        registra({**base_cfg, "seed": semilla}, tramo="val", resultado=s)
        print(
            f"  semilla {semilla}: ret {s['retorno_total']:7.1%} | sharpe {s['sharpe']:6.2f} "
            f"| maxDD {s['max_drawdown']:6.1%} | rot {s['rotacion_anual']:5.2f} "
            f"| caja {s['peso_caja_medio']:5.1%}"
        )

    # --- lectura sobre la DISTRIBUCIÓN, nunca sobre la mejor semilla (D10) ---
    def mediana(clave: str) -> float:
        return float(np.median([r[clave] for r in resultados]))

    def rango(clave: str) -> tuple[float, float]:
        v = [r[clave] for r in resultados]
        return float(np.percentile(v, 25)), float(np.percentile(v, 75))

    print("\nagente PPO sobre validación (mediana e intercuartil, D10):")
    for clave, fmt in [("retorno_total", "{:7.1%}"), ("sharpe", "{:7.2f}"),
                       ("max_drawdown", "{:7.1%}"), ("rotacion_anual", "{:7.2f}"),
                       ("peso_caja_medio", "{:7.1%}")]:
        q1, q3 = rango(clave)
        print(f"  {clave:16s} " + fmt.format(mediana(clave)) + f"   [{fmt.format(q1)}, {fmt.format(q3)}]")

    print(f"\nregistro de configuraciones (D10): {conteo()}")
    print(
        "\nRECORDATORIO: esto es el PILOTO de D21. Los números de arriba son "
        "diagnóstico de plomería sobre validación, NO hallazgos, y el tramo de "
        "prueba sigue sin tocarse."
    )


if __name__ == "__main__":
    main()
