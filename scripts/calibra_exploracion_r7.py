# -*- coding: utf-8 -*-
"""R7 — calibra la exploración de SAC y DDPG POR ROTACIÓN, como D22 hizo con PPO.

EL PROBLEMA. Con los defectos de SB3, la política estocástica de PPO rotaba 206
veces al año: el peaje del RUIDO se comía todo y el gradiente no podía aprender
a evitarlo (D22). SAC y DDPG tienen perillas equivalentes, y si se dejan en su
defecto la comparación de R7 mediría la exploración, no el algoritmo.

EL CRITERIO, el mismo de D22 y por la misma razón: la perilla se elige por la
ROTACIÓN QUE PRODUCE EL RUIDO, NUNCA por el retorno ni el Sharpe. Un
hiperparámetro elegido mirando el desempeño en validación es selección
encubierta y entraría al contador de D10. Por eso este script:
  * mide TODO sobre el tramo de ENTRENAMIENTO; la validación no se abre;
  * no calcula ni imprime retornos: solo rotación;
  * no escribe en el registro de configuraciones.

LA REFERENCIA ES PPO CON log_std=-2 EN MODO `delta`. D22 midió en modo `logits`
(31 rot/año); la forma adoptada hoy es `delta` (D2 enmendada), así que la
referencia se vuelve a medir acá, en las mismas condiciones que los otros dos.

POR QUÉ SAC SE MIDE DISTINTO. En PPO y en DDPG el ruido es un parámetro
EXTERNO a la red —log_std en PPO, la σ del ruido de acción en DDPG— y su
rotación se mide sobre una red SIN ENTRENAR, exactamente como D22. En SAC la
amplitud del ruido la PRODUCE LA RED y `ent_coef` solo actúa a través del
aprendizaje: una red de SAC sin entrenar rota lo mismo con cualquier ent_coef.
Así que para SAC se entrena un presupuesto corto y fijo SOBRE TRAIN y se mide la
rotación de su política estocástica sobre el mismo tramo. Sigue siendo un
criterio de comportamiento; se declara como tal.

Uso:
    python scripts/calibra_exploracion_r7.py
    python scripts/calibra_exploracion_r7.py --sigmas 0.02 0.05 0.1 0.2 --pasos-sac 20000
    python scripts/calibra_exploracion_r7.py --semillas 0 1 2 --sigmas 0.16 --ent-coefs 0.03
        (con `--sigmas` o `--ent-coefs` vacíos se salta ese algoritmo)
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

from train_ppo_oe1 import construye_env  # noqa: E402

from src.agents import construye_modelo, envuelve, exploracion  # noqa: E402
from src.env import load_panel, snapshot_cost_model  # noqa: E402
from src.env.folds import walk_forward  # noqa: E402

SALIDA = Path("data/interim/artefactos_oe1/exploracion_r7.json")
WARMUP = 250


def rotacion(env_envuelto, politica) -> float:
    """Corre el tramo completo con `politica(obs) -> accion` y devuelve la rotación anual."""
    obs, _ = env_envuelto.reset()
    done = False
    while not done:
        obs, _, term, trunc, _ = env_envuelto.step(politica(obs))
        done = term or trunc
    return float(env_envuelto.unwrapped.summary()["rotacion_anual"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fold", type=int, default=0)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--sigmas", type=float, nargs="*", default=[0.01, 0.02, 0.05, 0.1, 0.2, 0.3])
    ap.add_argument("--ent-coefs", type=float, nargs="*", default=[0.001, 0.01, 0.1])
    ap.add_argument("--pasos-sac", type=int, default=20_000,
                    help="presupuesto corto y FIJO de SAC antes de medir su rotación")
    ap.add_argument("--semillas", type=int, nargs="+", default=[0],
                    help="semillas por valor (DDPG: actor y ruido; SAC: entrenamiento)")
    ap.add_argument("--action-scale", type=float, default=0.05)
    ap.add_argument("--out", default=str(SALIDA))
    args = ap.parse_args()

    panel = load_panel(view="solo_mercado", warmup=WARMUP)
    costos = snapshot_cost_model(panel.tickers)
    primer_util = max(panel.features.warmup + 1, panel.first_tradable_index)
    p = walk_forward(panel.n_steps, n_folds=args.folds, start=primer_util)[args.fold]
    tramo = p.rango("train")
    cfg_extra = {"reward": "dsr", "rebalance_every": 1,
                 "action_mode": "delta", "action_scale": args.action_scale}
    d0, d1 = p.fechas(panel.dates, "train")

    print("=" * 84)
    print(f"R7 — EXPLORACIÓN POR ROTACIÓN · pliegue {p.idx} · TRAIN {d0} .. {d1}")
    print("sin validación, sin retornos, sin registro (criterio de D22)")
    print("=" * 84)

    def env_eval(algo: str):
        return envuelve(construye_env(panel, costos, tramo, entrenando=False,
                                      cfg_extra=cfg_extra), algo)

    res: dict = {"fold": p.idx, "tramo": [d0, d1], "action_scale": args.action_scale}

    # ---- referencia: PPO sin entrenar, log_std = -2 (D22) ----
    e = env_eval("ppo")
    ppo = construye_modelo("ppo", e, semilla=0, explora=exploracion("ppo", log_std=-2.0),
                           timesteps=1)
    ref_det = rotacion(e, lambda o: ppo.predict(o, deterministic=True)[0])
    ref_est = rotacion(e, lambda o: ppo.predict(o, deterministic=False)[0])
    ref_peaje = ref_est - ref_det
    res["ppo_log_std_-2"] = {"determinista": ref_det, "estocastica": ref_est,
                             "peaje_ruido": ref_peaje}
    print(f"\nREFERENCIA  PPO log_std=-2 sin entrenar   det {ref_det:7.2f}   "
          f"estocástica {ref_est:7.2f} rot/año")

    def resumen(peajes: list[float]) -> str:
        m, sd = float(np.mean(peajes)), float(np.std(peajes, ddof=1)) if len(peajes) > 1 else 0.0
        return (f"peaje {m:6.2f} ± {sd:5.2f}  ({m / ref_peaje:5.2f}x la referencia; "
                f"semillas {', '.join(f'{p:.2f}' for p in peajes)})")

    # ---- DDPG: actor sin entrenar + ruido gaussiano, como lo aplica SB3 ----
    # SB3 suma el ruido a la acción ya escalada a [-1, 1] y recorta: se replica.
    # Con varias semillas cambian a la vez la inicialización del actor y el ruido.
    if args.sigmas:
        print(f"\nDDPG (actor sin entrenar + N(0, σ) en el espacio [-1, 1]) · "
              f"{len(args.semillas)} semilla(s)")
        res["ddpg"] = {"semillas": args.semillas, "determinista": {}, "por_sigma": {}}
        actores = {}
        for sem in args.semillas:
            e = env_eval("ddpg")
            ddpg = construye_modelo("ddpg", e, semilla=sem,
                                    explora=exploracion("ddpg", sigma=0.1), timesteps=10_000)
            det = rotacion(e, lambda o, m=ddpg: m.predict(o, deterministic=True)[0])
            actores[sem] = (e, ddpg, det)
            res["ddpg"]["determinista"][str(sem)] = det
        for s in args.sigmas:
            peajes = []
            for sem, (e, ddpg, det) in actores.items():
                rng = np.random.default_rng(sem)
                r = rotacion(e, lambda o, s=s, m=ddpg, e=e, rng=rng: np.clip(
                    m.predict(o, deterministic=True)[0]
                    + rng.normal(0.0, s, size=e.action_space.shape), -1.0, 1.0))
                peajes.append(r - det)
            res["ddpg"]["por_sigma"][str(s)] = {
                "peajes": peajes, "media": float(np.mean(peajes)),
                "vs_referencia": float(np.mean(peajes)) / ref_peaje}
            print(f"  σ = {s:<6g} {resumen(peajes)}")

    # ---- SAC: presupuesto corto sobre TRAIN, rotación de su política estocástica ----
    if args.ent_coefs:
        print(f"\nSAC ({args.pasos_sac:,} pasos sobre train, luego rotación estocástica en train)"
              f" · {len(args.semillas)} semilla(s)")
        res["sac"] = {"pasos": args.pasos_sac, "semillas": args.semillas, "por_ent_coef": {}}
    for c in args.ent_coefs:
        corridas = []
        for sem in args.semillas:
            t0 = time.time()
            entreno = envuelve(construye_env(panel, costos, tramo, entrenando=True,
                                             cfg_extra=cfg_extra), "sac")
            sac = construye_modelo("sac", entreno, semilla=sem,
                                   explora=exploracion("sac", ent_coef=c),
                                   timesteps=args.pasos_sac)
            sac.learn(total_timesteps=args.pasos_sac, progress_bar=False)
            seg = time.time() - t0
            e = env_eval("sac")
            r_est = rotacion(e, lambda o: sac.predict(o, deterministic=False)[0])
            r_det = rotacion(e, lambda o: sac.predict(o, deterministic=True)[0])
            corridas.append({"semilla": sem, "estocastica": r_est, "determinista": r_det,
                             "peaje_ruido": r_est - r_det, "segundos_entrenamiento": seg,
                             "ms_por_paso": 1000.0 * seg / args.pasos_sac})
        peajes = [k["peaje_ruido"] for k in corridas]
        res["sac"]["por_ent_coef"][str(c)] = {
            "corridas": corridas, "media": float(np.mean(peajes)),
            "vs_referencia": float(np.mean(peajes)) / ref_peaje}
        print(f"  ent_coef = {c:<7g} {resumen(peajes)}")

    print("\nLECTURA (criterio de D22): se compara el PEAJE DEL RUIDO —rotación")
    print("estocástica MENOS determinista— contra el de PPO. En SAC la determinista")
    print("ya rota tras el entrenamiento corto: esa rotación es de la política")
    print("aprendida, no del ruido, y no es lo que ent_coef calibra. La elección la")
    print("registra el autor en D3; este script no la hace, para que quede escrita")
    print("ANTES de entrenar los brazos.")

    salida = Path(args.out)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nartefacto: {salida}")


if __name__ == "__main__":
    main()
