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
el tramo más favorable de los seis (+11.9% el 1/N) y las de los pliegues 1 y 2 fueron
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
    python scripts/ablacion_r8.py --algo sac --sac-ent-coef <calibrado> --out <ruta>

ALGORITMO (R7, D3 enmendada el 2026-09-26): `--algo` elige PPO, SAC o DDPG,
construidos por src/agents/algoritmos.py con la misma red y el mismo entorno.
SAC y DDPG exigen su perilla de exploracion EXPLICITA (calibrada por rotacion
en train, como D22) y un `--out` propio.

GUARDADO POR SEMILLA Y RETOMADO (2026-10-29). Hasta acá el JSON se escribía
recién al terminar una vista entera (9 corridas, ~10 h con DDPG) y el script no
sabía retomar: se perdió trabajo dos veces (09-oct y 11-oct). Ahora:
  * el artefacto se reescribe (atómicamente) después de CADA semilla, con
    `parcial: true` hasta que termina todo;
  * al arrancar, si `--out` ya existe —o si se pasa `--retoma <json>`, p. ej. un
    `.parcial.json` reconstruido desde el registro— se SALTAN las
    (vista, pliegue, semilla) que ya están, sin volver a anotarlas en D10;
  * retomar exige la MISMA configuración (algoritmo, recompensa, pasos,
    exploración, acción), el MISMO panel (sha256 de dataset_unificado) y la
    MISMA versión del simulador: mezclar corridas de dos paneles o de dos
    mecánicas de costo daría una ablación que no mide nada. Si el artefacto
    viejo no trae la huella del panel se avisa y se adopta la actual.
  * Por eso los `.parcial.json` de DDPG del 11-oct YA NO se pueden retomar: son
    anteriores a la corrección del simulador del 2026-10-29.
Subir `--seeds` sobre un artefacto completo lo EXTIENDE (3 -> 10) sin repetir.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
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
    costos_observados,
)
from src.env.features import VISTAS_ABLACION  # noqa: E402
from src.env.panel import DEFAULT_PANEL  # noqa: E402
from src.env.portfolio_env import VERSION_SIMULADOR  # noqa: E402
from src.env.folds import walk_forward  # noqa: E402
from src.env.registro import REGISTRO, conteo, registra  # noqa: E402

# Se IMPORTAN del piloto en vez de copiarse. Si el entorno de evaluación de la
# ablación se construyera distinto del entorno del piloto, los números no serían
# comparables y nadie se daría cuenta — es exactamente la deriva que este
# proyecto ya sufrió tres veces.
from train_ppo_oe1 import construye_env, evalua  # noqa: E402

from src.agents import (  # noqa: E402
    ALGORITMOS,
    config_registro,
    construye_modelo,
    envuelve,
    exploracion,
)

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


#: Argumentos que NO definen el experimento: se pueden cambiar al retomar.
#: `views` y `seeds` porque retomar una vista suelta o extender semillas es
#: justamente el caso de uso; `out`/`retoma` porque son rutas.
_ARGS_LIBRES = {"views", "seeds", "out", "retoma", "registro"}


def huella_panel(ruta: Path = DEFAULT_PANEL) -> str:
    """sha256 del parquet del panel: identifica CON QUÉ DATOS se entrenó."""
    h = hashlib.sha256()
    with Path(ruta).open("rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def compatibilidad(previo: dict, config: dict, panel_sha: str,
                   simulador: str = VERSION_SIMULADOR) -> list[str]:
    """Contra qué choca retomar `previo` con la configuración actual.

    Devuelve los AVISOS (claves que el artefacto viejo no trae y no se pueden
    verificar). Lanza ValueError ante cualquier diferencia real: retomar con
    otra configuración mezclaría dos experimentos en una sola tabla.

    La versión del simulador se EXIGE, no se avisa: un artefacto sin ella es
    anterior a la corrección de costos del 2026-10-29 y sus números no son
    comparables con los de ahora aunque la configuración (y el hash) coincidan.
    """
    sim_viejo = previo.get("simulador")
    if sim_viejo != simulador:
        raise ValueError(
            f"no se puede retomar: el simulador era {sim_viejo or 'anterior a 2026-10-29'} y ahora es "
            f"{simulador}. La misma configuración da otros números; hay que correr de nuevo."
        )
    avisos = []
    viejo = previo.get("config", {})
    # La perilla de exploración de OTRO algoritmo no define este experimento.
    ajenas = {"ppo": {"sac_ent_coef", "ddpg_sigma"},
              "sac": {"log_std", "ddpg_sigma"},
              "ddpg": {"log_std", "sac_ent_coef"}}.get(config.get("algo"), set())
    for clave, valor in config.items():
        if clave in _ARGS_LIBRES or clave in ajenas:
            continue
        if clave not in viejo:
            if valor is not None:
                avisos.append(f"el artefacto previo no anota '{clave}'; se asume {valor!r}")
            continue
        if viejo[clave] != valor:
            raise ValueError(
                f"no se puede retomar: '{clave}' era {viejo[clave]!r} y ahora es {valor!r}"
            )
    sha_viejo = previo.get("panel_sha256")
    if sha_viejo is None:
        avisos.append("el artefacto previo no anota el panel; se adopta el actual SIN verificar")
    elif sha_viejo != panel_sha:
        raise ValueError(
            f"no se puede retomar: el panel cambió (antes {sha_viejo[:12]}, ahora {panel_sha[:12]}). "
            "Mezclar corridas de dos paneles no mide el canal."
        )
    return avisos


def hechas(resultados: dict, vista: str, fold: int) -> dict[int, dict]:
    """Las semillas ya corridas de (vista, pliegue), indexadas por semilla."""
    filas = resultados["vistas"].get(vista, {}).get(f"pliegue{fold}", [])
    return {int(r["seed"]): r for r in filas}


def guarda(resultados: dict, salida: Path) -> None:
    """Escritura atómica: un corte a mitad de escritura no deja un JSON roto."""
    salida.parent.mkdir(parents=True, exist_ok=True)
    tmp = salida.with_name(salida.name + ".tmp")
    tmp.write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, salida)


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
    ap.add_argument("--reward", default="dsr",
                    choices=["dsr", "ddr", "logret", "mv", "logret_dd", "dsr_rot"])
    # D4 ENMENDADA (19-sep): los candidatos exigen su escala EXPLICITA. No hay
    # defecto a proposito —una constante que nadie recalibra cuando cambia el
    # universo es la trampa que este proyecto ya piso tres veces— asi que el
    # valor se pre-registra y viaja al registro de D10 con la configuracion.
    ap.add_argument("--lam", type=float, default=None,
                    help="lambda de mv / logret_dd (ver d4_tamiz_recompensas.py::calibra_escala)")
    ap.add_argument("--kappa", type=float, default=None,
                    help="kappa de dsr_rot")
    ap.add_argument("--algo", default="ppo", choices=list(ALGORITMOS))
    ap.add_argument("--log-std", type=float, default=-2.0, help="exploracion de PPO (D22)")
    ap.add_argument("--sac-ent-coef", type=float, default=None,
                    help="coeficiente de entropia FIJO de SAC; sin defecto (calibrar por rotacion)")
    ap.add_argument("--ddpg-sigma", type=float, default=None,
                    help="sigma del ruido de accion de DDPG; sin defecto (calibrar por rotacion)")
    ap.add_argument("--action-mode", default="delta", choices=["delta", "logits"])
    ap.add_argument("--action-scale", type=float, default=0.05)
    ap.add_argument("--rebalance-every", type=int, default=1)
    ap.add_argument("--n-envs", type=int, default=None,
                    help="entornos en paralelo (defecto: 4 para PPO, 1 para SAC/DDPG)")
    # El artefacto se PARAMETRIZA porque este script ya no corre una sola vez:
    # una corrida parcial (una vista suelta, u otra recompensa) sobrescribia el
    # JSON de la ablacion entera y se perdia. El defecto no cambia, asi que las
    # invocaciones viejas siguen escribiendo donde siempre.
    ap.add_argument("--out", default=str(SALIDA),
                    help="ruta del artefacto JSON de salida (si existe, se RETOMA)")
    ap.add_argument("--retoma", default=None,
                    help="artefacto previo del que retomar (defecto: --out si existe); "
                         "p. ej. un .parcial.json reconstruido desde el registro")
    # Solo para PROBAR el script sin ensuciar el registro de D10, que es
    # append-only: una corrida de humo anotada ahí contaría como estrategia.
    ap.add_argument("--registro", default=str(REGISTRO), help=argparse.SUPPRESS)
    args = ap.parse_args()
    salida = Path(args.out)
    origen = Path(args.retoma) if args.retoma else (salida if salida.exists() else None)
    if origen is not None and not origen.exists():
        ap.error(f"--retoma: no existe {origen}")
    try:
        explora = exploracion(args.algo, log_std=args.log_std,
                              ent_coef=args.sac_ent_coef, sigma=args.ddpg_sigma)
    except ValueError as e:
        ap.error(str(e))
    if args.algo != "ppo" and args.action_mode != "delta":
        ap.error(f"{args.algo.upper()} solo corre con --action-mode delta (ver AccionAcotada)")
    if args.algo != "ppo" and salida == SALIDA:
        ap.error(f"{args.algo.upper()} necesita --out propio: el defecto es el artefacto de la ablacion PPO")
    # Off-policy con 1 entorno: con varios, SB3 hace un paso de gradiente cada
    # n_envs transiciones y cambia la razon de repeticion del replay.
    n_envs = args.n_envs if args.n_envs is not None else (4 if args.algo == "ppo" else 1)

    from stable_baselines3.common.env_util import make_vec_env

    t0 = time.time()
    print("=" * 84)
    print(f"R8 — ABLACIÓN DE CANALES  ·  {args.algo.upper()}  {explora}")
    print("=" * 84)
    print(f"vistas   : {', '.join(args.views)}")
    print(f"pliegues : {args.folds}  ·  semillas: {args.seeds}  ·  pasos: {args.timesteps:,}")
    print(f"total    : {len(args.views) * args.folds * args.seeds} corridas")
    print("EL TRAMO DE PRUEBA NO SE TOCA: todo se evalúa sobre val (D21).\n")

    reward_kwargs: dict = {}
    if args.lam is not None:
        reward_kwargs["lam"] = args.lam
    if args.kappa is not None:
        reward_kwargs["kappa"] = args.kappa
    if args.reward in ("mv", "logret_dd") and "lam" not in reward_kwargs:
        ap.error(f"la recompensa {args.reward} necesita --lam (pre-registrado)")
    if args.reward == "dsr_rot" and "kappa" not in reward_kwargs:
        ap.error("la recompensa dsr_rot necesita --kappa (pre-registrado)")

    cfg_extra = {
        "reward": args.reward,
        "reward_kwargs": reward_kwargs,
        "rebalance_every": args.rebalance_every,
        "action_mode": args.action_mode,
        "action_scale": args.action_scale,
    }

    panel_sha = huella_panel()
    resultados: dict = {"config": vars(args), "vistas": {}, "baselines": {}, "dims": {}}
    if origen is not None:
        previo = json.loads(origen.read_text(encoding="utf-8"))
        try:
            avisos = compatibilidad(previo, vars(args), panel_sha)
        except ValueError as e:
            ap.error(f"{e}  [{origen}]")
        resultados["vistas"] = previo.get("vistas", {})
        resultados["retomas"] = previo.get("retomas", [])
        if "nota" in previo:
            resultados["nota_origen"] = previo["nota"]
        resultados["retomas"].append({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "desde": str(origen),
            "avisos": avisos,
        })
        n_prev = sum(len(f) for v in resultados["vistas"].values() for f in v.values())
        print(f"RETOMA desde {origen}: {n_prev} corridas ya hechas (no se repiten ni se re-registran)")
        for a in avisos:
            print(f"  aviso: {a}")
    resultados["panel_sha256"] = panel_sha
    resultados["simulador"] = VERSION_SIMULADOR
    resultados["parcial"] = True

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
        costos = costos_observados(panel)
        print(f"\n{'=' * 84}\n{vista}  ({len(panel.features.columns)} cols/activo · obs {dim})\n{'=' * 84}")
        resultados["vistas"].setdefault(vista, {})

        for p in pliegues:
            if vista == args.views[0]:
                # Deterministas y baratos: se recalculan siempre, también al retomar.
                resultados["baselines"][f"pliegue{p.idx}"] = baselines_del_tramo(
                    panel, costos, p.rango("val")
                )
            base_cfg = {
                "view": vista,
                "reward": args.reward,
                "reward_kwargs": reward_kwargs,
                "rebalance_every": args.rebalance_every,
                "fold": p.idx,
                "action_mode": args.action_mode,
                "action_scale": args.action_scale,
                "timesteps": args.timesteps,
                # Para PPO son exactamente {algoritmo, net_arch, log_std_init},
                # como antes: el hash de sus configuraciones no cambia.
                **config_registro(args.algo, explora),
            }
            por_semilla = hechas(resultados, vista, p.idx)
            for semilla in range(args.seeds):
                if semilla in por_semilla:
                    print(f"  pliegue{p.idx} s{semilla}: ya estaba, se salta")
                    continue
                entorno = make_vec_env(
                    lambda: envuelve(
                        construye_env(
                            panel, costos, p.rango("train"), entrenando=True, cfg_extra=cfg_extra
                        ),
                        args.algo,
                    ),
                    n_envs=n_envs,
                    seed=semilla,
                )
                modelo = construye_modelo(args.algo, entorno, semilla=semilla,
                                          explora=explora, timesteps=args.timesteps)
                modelo.learn(total_timesteps=args.timesteps, progress_bar=False)
                s = evalua(modelo, panel, costos, p.rango("val"), cfg_extra, algo=args.algo)
                s["seed"] = semilla
                # En el RESULTADO, no en la config: así el hash de D10 no cambia
                # pero el registro distingue corridas de antes y después.
                s["simulador"] = VERSION_SIMULADOR
                por_semilla[semilla] = s
                # D10: se anota ANTES de mirar si el resultado gusta.
                registra({**base_cfg, "seed": semilla}, tramo="val", resultado=s,
                          ruta=args.registro)
                resultados["vistas"][vista][f"pliegue{p.idx}"] = [
                    por_semilla[k] for k in sorted(por_semilla)
                ]
                guarda(resultados, salida)
                print(
                    f"  pliegue{p.idx} s{semilla}: ret {s['retorno_total']:+7.1%} "
                    f"sharpe {s['sharpe']:6.2f} sortino {s['sortino']:6.2f} "
                    f"maxDD {s['max_drawdown']:+6.1%} rot {s['rotacion_anual']:5.2f} "
                    f"caja {s['peso_caja_medio']:5.1%}  [{(time.time()-t0)/60:.0f} min]"
                )
            resultados["vistas"][vista][f"pliegue{p.idx}"] = [
                por_semilla[k] for k in sorted(por_semilla)
            ]
            guarda(resultados, salida)

    resultados["parcial"] = False
    guarda(resultados, salida)

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
                    # Pareo POR SEMILLA, no por posición: tras un retomado las
                    # dos vistas pueden no tener las mismas semillas.
                    a = hechas(resultados, vista, p.idx)
                    b = hechas(resultados, base_v, p.idx)
                    d = [a[k][clave] - b[k][clave] for k in sorted(a.keys() & b.keys())]
                    todo += d
                    celdas.append(f"{np.median(d):>+12.3f}")
                print(f"    {vista:<26}" + "".join(celdas) + f"{np.median(todo):>+12.3f}")

    print(f"\n\nregistro de configuraciones (D10): {conteo(args.registro)}")
    print(f"artefacto: {salida}")
    print(f"\nterminado en {(time.time()-t0)/60:.1f} min")
    print(
        "\nRECORDATORIO: 3 semillas es DIAGNÓSTICO, no resultado. D10 pide 10 "
        "semillas y pre-registro antes de reportar nada como hallazgo, y D25 "
        "sigue abierta: estos agentes están subentrenados por igual."
    )


if __name__ == "__main__":
    main()
