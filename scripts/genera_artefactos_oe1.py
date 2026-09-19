# -*- coding: utf-8 -*-
"""Precalcula TODO lo que el notebook de OE1 grafica, para que el notebook no entrene.

POR QUÉ EXISTE: el notebook `notebooks/OE1_entorno_y_agente.ipynb` está pensado
para abrirse y correrse DELANTE DEL ASESOR. Entrenar PPO ahí adentro son ~60
minutos; graficar artefactos son 3 segundos. Este script hace el trabajo pesado
una vez y deja los resultados en `data/interim/artefactos_oe1/`.

QUÉ SE GUARDA
    panel.json          hechos del panel: fechas, activos, cobertura, tasa
    costos.json         costo de ida y vuelta por activo y banda de no-operación
    baselines.npz       curvas de patrimonio de las políticas de referencia
    baselines.json      resumen de cada política (horizonte completo y por pliegue)
    banda_nula.json     distribución de 200 carteras Dirichlet
    pliegues.json       walk-forward con embargo (D10), expanding y rolling
    exploracion.json    rotación contra log_std, sin entrenar (D22)
    agente_*.npz/json   piloto de D21: PPO por modo de acción y semilla
    modelos/*.zip       políticas entrenadas — MEDIO DE VERIFICACIÓN de R7

MEDIO DE VERIFICACIÓN DE R7. El documento de tesis pide "curvas de entrenamiento;
modelos almacenados" y "convergencia estable de las curvas de recompensa en al
menos 3 semillas por algoritmo". Hasta el 2026-09-11 se entrenaba con verbose=0 y
sin `model.save()`: el agente existía pero R7 NO SE ACREDITABA. Acá se registran
las dos cosas.

  OJO CON LA CURVA: con `random_start` los episodios tienen largo variable, así
  que la recompensa ACUMULADA por episodio mezcla "lo bien que le fue" con "cuán
  largo fue". Se guarda también la recompensa POR PASO, que es la comparable, y
  es la que hay que graficar.

DISCIPLINA DE D10. Las corridas de PPO se anotan en el registro append-only
igual que siempre, con `replica_para_figuras: True` dentro de `resultado`. Ese
campo NO entra al hash de la configuración, así que el contador de
`configuraciones_distintas` —que es el que alimenta el Sharpe deflactado— no se
mueve: volver a correr una configuración YA probada para dibujarla no es una
prueba nueva de estrategia. El contador de `corridas` sí sube, que es lo honesto.

EL TRAMO DE PRUEBA NO SE TOCA (D21). Los pliegues se calculan enteros para poder
dibujarlos, pero ninguna política se evalúa sobre `test`.

Uso:
    python scripts/genera_artefactos_oe1.py              # todo (~60 min)
    python scripts/genera_artefactos_oe1.py --sin-agente # solo lo barato (~1 min)
    python scripts/genera_artefactos_oe1.py --timesteps 40000 --seeds 2
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.env import (  # noqa: E402
    CashOnly,
    EnvConfig,
    EqualWeight,
    Markowitz,
    PortfolioEnv,
    RandomDirichlet,
    load_panel,
    run_policy,
    snapshot_cost_model,
    zero_cost_model,
)
from src.env.costs import SPREAD_SNAPSHOT_BPS  # noqa: E402
from src.env.folds import EMBARGO_DEFAULT, walk_forward  # noqa: E402
from src.env.registro import conteo, registra  # noqa: E402

SALIDA = Path("data/interim/artefactos_oe1")
VISTA = "solo_mercado"  # la del piloto de D21
WARMUP = 250
N_FOLDS = 3
N_NULL = 200  # carteras de la banda nula. 60 en el smoke; acá alcanza para un histograma
# D26 — ventana de estimación del baseline Markowitz, en días bursátiles. Es un
# parámetro PRE-REGISTRABLE, no un botón: se fija por convención de la
# literatura (un año) y se reporta 126/500 como sensibilidad, nunca se elige
# mirando cuál da mejor número.
VENTANA_MARKOWITZ = 252
MIN_OBS_MARKOWITZ = 60


# --------------------------------------------------------------------------- io
def escribe_json(nombre: str, obj) -> None:
    ruta = SALIDA / nombre
    ruta.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"   -> {ruta}")


def fechas_str(dates: np.ndarray) -> list[str]:
    return [str(d)[:10] for d in dates]


# ------------------------------------------------------------------ 1. el panel
def hechos_del_panel(panel) -> dict:
    """Lo que hay que poder afirmar sobre el panel sin volver a abrir el parquet."""
    primer_util = max(panel.features.warmup + 1, panel.first_tradable_index)
    no_trade = panel.no_trade
    stale = panel.stale
    return {
        "n_fechas": int(panel.n_steps),
        "n_activos": int(panel.n_assets),
        "tickers": list(panel.tickers),
        "fecha_inicio": str(panel.dates[0])[:10],
        "fecha_fin": str(panel.dates[-1])[:10],
        "primer_dia_con_los_7": str(panel.dates[panel.first_tradable_index])[:10],
        "primer_dia_operable": str(panel.dates[primer_util])[:10],
        "primer_indice_operable": int(primer_util),
        "warmup_D6": int(panel.features.warmup),
        "features_por_activo": int(panel.features.n_features),
        "columnas_features": list(panel.features.columns),
        "dim_observacion": int(panel.features.flat_dim() + panel.n_assets + 1 + 2),
        # D8: is_no_trade PROHÍBE, is_stale solo encarece. Se reportan por separado
        # porque se confunden con facilidad y significan cosas distintas.
        "frac_no_trade": {t: float(no_trade[:, j].mean()) for j, t in enumerate(panel.tickers)},
        "frac_stale": {t: float(stale[:, j].mean()) for j, t in enumerate(panel.tickers)},
        "frac_dias_los_7_operables": float((~no_trade).all(axis=1).mean()),
        "frac_dias_los_7_con_precio_propio": float((~stale).all(axis=1).mean()),
        "tasa_ref_anual_media_pct": float(panel.rf_daily.mean() * 365 * 100),
        "tasa_ref_anual_min_pct": float(panel.rf_daily.min() * 365 * 100),
        "tasa_ref_anual_max_pct": float(panel.rf_daily.max() * 365 * 100),
    }


def dimension_por_vista() -> dict:
    """Cuánto crece la observación con cada vista de la ablación de R8."""
    out = {}
    for vista in ("solo_mercado", "mercado_macro", "mercado_sentimiento",
                  "mercado_fundamentales", "completa"):
        p = load_panel(view=vista, warmup=WARMUP)
        out[vista] = {
            "features_por_activo": int(p.features.n_features),
            "dim_observacion": int(p.features.flat_dim() + p.n_assets + 1 + 2),
            "columnas": list(p.features.columns),
        }
    return out


# ----------------------------------------------------------------- 2. los costos
def hechos_de_costos(panel, costos) -> dict:
    nocionales = [5_000, 9_302, 25_000, 100_000, 250_000, 1_000_000]
    curva = {
        str(n): {t: float(b) for t, b in zip(panel.tickers, costos.roundtrip_bps(notional=n))}
        for n in nocionales
    }
    return {
        "spread_snapshot_ida_vuelta_bps": {t: SPREAD_SNAPSHOT_BPS[t] for t in panel.tickers},
        "comision_pct": costos.commission_rate,
        "comision_minima_pen": costos.min_fee,
        "igv": costos.igv,
        "derechos_mercado": costos.fees_rate,
        "banda_no_operacion_pen": float(costos.band_notional()),
        "roundtrip_bps_por_nocional": curva,
        "fuente": "Renta 4 Perú (web, 2026-09-03) + snapshot de puntas BVL 2026-07-27. "
                  "PENDIENTE: tarifario primario y SERIE HISTÓRICA de puntas (Bloomberg).",
    }


# -------------------------------------------------------------- 3. los baselines
def _markowitz(**kw):
    """Fábrica, no instancia: cada escenario necesita su propia política porque
    Markowitz lleva estado (la cartera vigente y los contadores de D26)."""
    return lambda: Markowitz(
        window=VENTANA_MARKOWITZ, min_obs=MIN_OBS_MARKOWITZ, **kw
    )


# El cuarto campo es una FÁBRICA de política. Antes era una etiqueta con un
# `if` adentro de corre_baselines; con tres baselines más eso se volvía una
# cadena de elifs y el próximo baseline se agregaría en dos lugares.
#
# MARKOWITZ VA A RESOLUCIÓN MENSUAL por el requisito de equidad de D10: cada
# baseline corre con SU frecuencia. Re-optimizar una media-varianza todos los
# días bajo 111-323 pbs de costo sería armar un rival de paja — el mismo error
# que la primera versión de la banda nula, que re-sorteaba cada 21 días y
# medía el costo de rotar en vez de la suerte de la asignación.
ESCENARIOS = [
    ("1/N diario sin costo", "sin_costo", 1, EqualWeight),
    ("1/N diario", "costo", 1, EqualWeight),
    ("1/N semanal", "costo", 5, EqualWeight),
    ("1/N mensual", "costo", 21, EqualWeight),
    ("1/N trimestral", "costo", 63, EqualWeight),
    ("comprar y mantener", "costo", 10**9, EqualWeight),
    ("solo caja", "costo", 1, CashOnly),
    ("markowitz tangencia", "costo", 21, _markowitz()),
    ("markowitz tangencia-LW", "costo", 21, _markowitz(shrinkage="ledoit_wolf")),
    ("markowitz min-var", "costo", 21, _markowitz(objetivo="min_var")),
]


def corre_baselines(panel, costos, sin_costo, rango: tuple[int, int] | None) -> tuple[dict, dict]:
    """Corre las políticas de referencia. `rango=None` es el horizonte completo."""
    resumenes, curvas = {}, {}
    for etiqueta, cm, freq, fabrica in ESCENARIOS:
        modelo = sin_costo if cm == "sin_costo" else costos
        politica = fabrica()
        cfg = EnvConfig(action_mode="weights", rebalance_every=freq)
        if rango is not None:
            cfg.start_index, cfg.end_index = rango
        env = PortfolioEnv(panel, modelo, cfg)
        res = run_policy(env, politica)
        resumenes[etiqueta] = res["summary"]
        # D26(b): cuántas veces la media-varianza declaró que NINGÚN activo
        # supera a la tasa libre de riesgo y se fue a caja. No es telemetría:
        # es el resultado de que la teoría clásica también recomienda salirse
        # del mercado en este universo, y va reportado.
        if getattr(politica, "n_resueltos", 0):
            resumenes[etiqueta]["veces_degenerado"] = politica.n_degenerado
            resumenes[etiqueta]["veces_optimizado"] = politica.n_resueltos
        # Peso medio por casilla: con Markowitz concentrándose al 100% en un
        # activo, la tabla de retornos sola no cuenta lo que pasó.
        w = np.asarray(res["weights"])
        resumenes[etiqueta]["peso_medio"] = {
            t: float(x) for t, x in zip(list(panel.tickers) + ["CAJA"], w.mean(axis=0))
        }
        curvas[etiqueta] = res["equity"]
        curvas[etiqueta + "__fechas"] = np.asarray(fechas_str(res["dates"]))
    return resumenes, curvas


def banda_nula(panel, costos, rango: tuple[int, int] | None = None) -> dict:
    """D10 — qué consigue el AZAR en este universo, con las mismas restricciones."""
    out = {}
    for freq, etiqueta in [(21, "rebalanceo mensual"), (10**9, "sin rebalanceo")]:
        finales, sharpes, pesos = [], [], []
        for semilla in range(N_NULL):
            cfg = EnvConfig(action_mode="weights", rebalance_every=freq)
            if rango is not None:
                cfg.start_index, cfg.end_index = rango
            env = PortfolioEnv(panel, costos, cfg)
            res = run_policy(env, RandomDirichlet(seed=semilla))
            finales.append(res["summary"]["retorno_total"])
            sharpes.append(res["summary"]["sharpe"])
            pesos.append(res["weights"][-1].tolist())
        out[etiqueta] = {
            "n": N_NULL,
            "retornos": finales,
            "sharpes": sharpes,
            "p5": float(np.percentile(finales, 5)),
            "mediana": float(np.median(finales)),
            "p95": float(np.percentile(finales, 95)),
        }
    return out


# --------------------------------------- 3b. ¿cambia el régimen? (asesor, 09-11)
def _rasgos(prices: np.ndarray, a: int, b: int) -> dict:
    """Rasgos de régimen de un tramo: deriva, volatilidad y co-movimiento."""
    r = np.diff(np.log(prices[a:b]), axis=0)
    vol = float(np.mean(r.std(axis=0)) * np.sqrt(252))
    c = np.corrcoef(r, rowvar=False)
    fuera = ~np.eye(c.shape[0], dtype=bool)
    return {
        "retorno_anual": float(np.mean(r.mean(axis=0)) * 252),
        "vol_anual": vol,
        "corr_media": float(np.nanmean(c[fuera])),
        "dias": int(b - a),
    }


def compara_regimenes(panel, expanding, rolling) -> dict:
    """¿La ventana móvil se PARECE MÁS a su validación que la expandida?

    Es la pregunta del asesor convertida en medición, y no cuesta nada en el
    contador de D10: son estadísticos del panel, no estrategias entrenadas.
    Si la data vieja realmente estorba, el tramo de entrenamiento ROLLING debería
    estar más cerca de su validación que el EXPANDING en volatilidad y
    co-movimiento — que es lo que gobierna a un agente de portafolio.
    """
    out = {}
    for k, (pe, pr) in enumerate(zip(expanding, rolling)):
        val = _rasgos(panel.prices, *pe.val)
        exp = _rasgos(panel.prices, *pe.train)
        rol = _rasgos(panel.prices, *pr.train)
        out[f"pliegue{k}"] = {
            "val": val, "train_expanding": exp, "train_rolling": rol,
            "distancia_expanding": {
                "vol": abs(exp["vol_anual"] - val["vol_anual"]),
                "corr": abs(exp["corr_media"] - val["corr_media"]),
            },
            "distancia_rolling": {
                "vol": abs(rol["vol_anual"] - val["vol_anual"]),
                "corr": abs(rol["corr_media"] - val["corr_media"]),
            },
        }
        # El pliegue 0 es un EMPATE POR CONSTRUCCIÓN: la ventana móvil se define
        # con el largo de su propio entrenamiento, así que ambos esquemas miran
        # exactamente el mismo tramo. Declararlo evita contar un empate como
        # victoria de uno de los dos.
        identico = pe.train == pr.train
        gana = []
        for m in ("vol", "corr"):
            de = out[f"pliegue{k}"]["distancia_expanding"][m]
            dr = out[f"pliegue{k}"]["distancia_rolling"][m]
            gana.append("idéntico" if identico else ("rolling" if dr < de else "expanding"))
        out[f"pliegue{k}"]["mas_parecido_a_val"] = {"vol": gana[0], "corr": gana[1]}
        out[f"pliegue{k}"]["tramos_identicos"] = bool(identico)
        print(f"   pliegue {k}: val vol {val['vol_anual']:.3f} corr {val['corr_media']:.3f} | "
              f"exp {exp['vol_anual']:.3f}/{exp['corr_media']:.3f} | "
              f"rol {rol['vol_anual']:.3f}/{rol['corr_media']:.3f} | "
              f"más cerca: vol={gana[0]}, corr={gana[1]}")
    return out


# ------------------------------------------------ 4. exploración sin entrenar (D22)
def rotacion_contra_log_std(panel, costos, rango, escalas=(0.0, -1.0, -2.0, -3.0)) -> dict:
    """D22 — cuánto rota el RUIDO de PPO, antes de que el agente aprenda nada.

    Es la medición que define el criterio de calibración: la escala de
    exploración se elige por ROTACIÓN, nunca por retorno. Una red sin entrenar
    no tiene señal, así que toda la rotación que se ve acá es peaje del ruido.
    """
    from stable_baselines3 import PPO

    out = {}
    cfg_base = dict(start_index=rango[0], end_index=rango[1],
                    action_mode="logits", reward="dsr")
    env_ref = PortfolioEnv(panel, costos, EnvConfig(**cfg_base))
    modelo = PPO("MlpPolicy", env_ref, seed=0, verbose=0,
                 policy_kwargs={"net_arch": [64, 64], "log_std_init": 0.0})

    for deterministica in (True, False):
        for log_std in ([None] if deterministica else escalas):
            if log_std is not None:
                with __import__("torch").no_grad():
                    modelo.policy.log_std.fill_(float(log_std))
            env = PortfolioEnv(panel, costos, EnvConfig(**cfg_base))
            obs, _ = env.reset()
            done = False
            while not done:
                accion, _ = modelo.predict(obs, deterministic=deterministica)
                obs, _, term, trunc, _ = env.step(accion)
                done = term or trunc
            clave = "determinista" if deterministica else f"estocastica_log_std_{log_std:g}"
            s = env.summary()
            out[clave] = {"rotacion_anual": s["rotacion_anual"], "costo_total": s["costo_total"]}
            print(f"   {clave:28s} rot/año {s['rotacion_anual']:8.2f}  costo S/{s['costo_total']:,.0f}")
    return out


# ------------------------------------------------------------------- 5. el agente
def _callback_curva():
    """Callback que registra la curva de recompensa de entrenamiento (R7).

    Lee `ep_info_buffer`, que SB3 llena porque `make_vec_env` envuelve cada
    entorno en un `Monitor`. Guarda la recompensa acumulada Y la recompensa por
    paso: con episodios de largo variable (random_start) solo la segunda es
    comparable entre puntos de la curva.
    """
    from stable_baselines3.common.callbacks import BaseCallback

    class CurvaEntrenamiento(BaseCallback):
        def __init__(self) -> None:
            super().__init__()
            self.pasos: list[int] = []
            self.recompensa_ep: list[float] = []
            self.recompensa_paso: list[float] = []
            self.largo_ep: list[float] = []

        def _on_step(self) -> bool:  # obligatorio en la interfaz de SB3
            return True

        def _on_rollout_end(self) -> None:
            buf = [e for e in (self.model.ep_info_buffer or []) if e.get("l", 0) > 0]
            if not buf:
                return
            r = np.array([e["r"] for e in buf], dtype=float)
            ln = np.array([e["l"] for e in buf], dtype=float)
            self.pasos.append(int(self.num_timesteps))
            self.recompensa_ep.append(float(r.mean()))
            self.recompensa_paso.append(float((r / ln).mean()))
            self.largo_ep.append(float(ln.mean()))

    return CurvaEntrenamiento()


def entrena_y_evalua(panel, costos, pliegue, modo: str, semilla: int, args) -> tuple[dict, dict]:
    """Un entrenamiento (train) y su evaluación determinista (val). NUNCA test."""
    from stable_baselines3 import PPO
    from stable_baselines3.common.env_util import make_vec_env

    cfg_extra = dict(reward=args.reward, rebalance_every=1,
                     action_mode=modo, action_scale=args.action_scale)

    def hace_env():
        a, b = pliegue.train
        return PortfolioEnv(panel, costos,
                            EnvConfig(start_index=a, end_index=b, random_start=True, **cfg_extra))

    vec = make_vec_env(hace_env, n_envs=args.n_envs, seed=semilla)
    modelo = PPO("MlpPolicy", vec, seed=semilla, verbose=0, n_steps=512, batch_size=256,
                 gamma=0.99, ent_coef=0.0,
                 policy_kwargs={"net_arch": [64, 64], "log_std_init": args.log_std})
    curva_cb = _callback_curva()
    t0 = time.time()
    modelo.learn(total_timesteps=args.timesteps, progress_bar=False, callback=curva_cb)
    minutos = (time.time() - t0) / 60

    # --- R7: el modelo entrenado se ALMACENA, no se descarta ---
    dir_modelos = SALIDA / "modelos"
    dir_modelos.mkdir(parents=True, exist_ok=True)
    ruta_modelo = dir_modelos / f"ppo_{modo}_f{pliegue.idx}_s{semilla}.zip"
    modelo.save(ruta_modelo)

    a, b = pliegue.val
    env = PortfolioEnv(panel, costos, EnvConfig(start_index=a, end_index=b, **cfg_extra))
    obs, _ = env.reset()
    done = False
    while not done:
        accion, _ = modelo.predict(obs, deterministic=True)
        obs, _, term, trunc, _ = env.step(accion)
        done = term or trunc

    resumen = env.summary()
    pesos = np.asarray(env.history["weights"])
    resumen["peso_caja_medio"] = float(pesos[:, -1].mean())
    resumen["minutos_entrenamiento"] = minutos
    resumen["modelo_guardado"] = str(ruta_modelo.relative_to(SALIDA))
    for j, t in enumerate(panel.tickers):
        resumen[f"peso_medio_{t}"] = float(pesos[:, j].mean())

    curvas = {
        "equity": env.equity_curve,
        "pesos": pesos,
        "fechas": np.asarray(fechas_str(np.asarray(env.history["date"]))),
        "costo": np.asarray(env.history["cost"]),
        "turnover": np.asarray(env.history["turnover"]),
        # R7: la curva de entrenamiento, que es el medio de verificación.
        "tr_pasos": np.asarray(curva_cb.pasos, dtype=float),
        "tr_recompensa_ep": np.asarray(curva_cb.recompensa_ep, dtype=float),
        "tr_recompensa_paso": np.asarray(curva_cb.recompensa_paso, dtype=float),
        "tr_largo_ep": np.asarray(curva_cb.largo_ep, dtype=float),
    }

    cfg_registro = {
        "view": VISTA, "reward": args.reward, "rebalance_every": 1, "fold": pliegue.idx,
        "action_mode": modo, "action_scale": args.action_scale,
        "log_std_init": args.log_std, "timesteps": args.timesteps,
        "algoritmo": "PPO", "net_arch": [64, 64], "seed": semilla,
    }
    # `replica_para_figuras` y `panel` van en RESULTADO, no en config: no cambian
    # el hash y por lo tanto no inflan el contador de configuraciones distintas
    # de D10.
    #
    # POR QUÉ SE ESTAMPA EL PANEL. El 2026-09-12 se corrigió el desfase de un día
    # de la ingesta de la BVL (docs/hallazgos_desfase_fecha_bvl.txt) y el panel se
    # regeneró. Las corridas anteriores a esa fecha están EN CUARENTENA: miden la
    # misma estrategia sobre datos mal alineados. Sin esta marca, el registro
    # append-only mezclaría dos poblaciones y nadie podría separarlas después.
    #
    # NO SE CUENTAN COMO CONFIGURACIONES NUEVAS, y el argumento es que D2 y D22
    # se decidieron por criterios de COMPORTAMIENTO (rotación), no de desempeño,
    # así que las corridas en cuarentena no constituyen selección sobre el
    # resultado. Si algún día se decide contarlas, la marca permite hacerlo.
    registra(cfg_registro, tramo="val",
             resultado={**resumen, "replica_para_figuras": True,
                        "panel": "post_fix_fecha_20260912"})
    return resumen, curvas


# ------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sin-agente", action="store_true", help="solo lo barato (~1 min)")
    ap.add_argument("--timesteps", type=int, default=150_000)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--fold", type=int, default=0)
    ap.add_argument("--reward", default="dsr")
    ap.add_argument("--log-std", type=float, default=-2.0)
    ap.add_argument("--action-scale", type=float, default=0.05)
    ap.add_argument("--n-envs", type=int, default=4)
    args = ap.parse_args()

    SALIDA.mkdir(parents=True, exist_ok=True)
    t_inicio = time.time()

    print("[1/6] panel")
    panel = load_panel(view=VISTA, warmup=WARMUP)
    costos = snapshot_cost_model(panel.tickers)
    sin_costo = zero_cost_model(panel.tickers)
    escribe_json("panel.json", {**hechos_del_panel(panel), "vistas": dimension_por_vista()})

    print("[2/6] costos")
    escribe_json("costos.json", hechos_de_costos(panel, costos))

    print("[3/6] pliegues (walk-forward, D10)")
    primer_util = max(panel.features.warmup + 1, panel.first_tradable_index)
    pliegues = walk_forward(panel.n_steps, n_folds=N_FOLDS, start=primer_util)

    def describe(ps) -> list[dict]:
        return [
            {
                "idx": p.idx,
                **{
                    tramo: {
                        "i0": p.rango(tramo)[0], "i1": p.rango(tramo)[1],
                        "desde": p.fechas(panel.dates, tramo)[0],
                        "hasta": p.fechas(panel.dates, tramo)[1],
                        "dias": p.rango(tramo)[1] - p.rango(tramo)[0],
                    }
                    for tramo in ("train", "val", "test")
                },
            }
            for p in ps
        ]

    # Ventana MÓVIL con el largo del primer pliegue: es la alternativa que
    # planteó el asesor (2026-09-11). Se describe para poder COMPARARLA, no
    # porque esté adoptada; la decisión es pre-registrable, ver folds.py.
    largo_primero = pliegues[0].train[1] - pliegues[0].train[0]
    rolling = walk_forward(panel.n_steps, n_folds=N_FOLDS, start=primer_util,
                           train_len=largo_primero)
    escribe_json("pliegues.json", {
        "embargo_dias": EMBARGO_DEFAULT,
        "dias_utilizables": int(panel.n_steps - primer_util),
        "esquema_adoptado": "expanding",
        "largo_ventana_movil": int(largo_primero),
        "pliegues": describe(pliegues),
        "pliegues_rolling": describe(rolling),
    })

    print("[3b/6] ¿cambia el régimen? expanding vs rolling contra su validación")
    escribe_json("regimenes.json", compara_regimenes(panel, pliegues, rolling))

    print("[4/6] baselines")
    curvas_npz: dict[str, np.ndarray] = {}
    resumen_base: dict[str, dict] = {}

    r, c = corre_baselines(panel, costos, sin_costo, None)
    resumen_base["horizonte_completo"] = r
    curvas_npz.update({f"completo__{k}": v for k, v in c.items()})
    for etiqueta, s in r.items():
        deg = (f" degen {s['veces_degenerado']}/{s['veces_optimizado']}"
               if "veces_degenerado" in s else "")
        print(f"   {etiqueta:24s} ret {s['retorno_total']:8.1%} anual {s['retorno_anualizado']:7.1%} "
              f"sharpe {s['sharpe']:6.2f} sortino {s['sortino']:6.2f} "
              f"maxDD {s['max_drawdown']:7.1%} rot {s['rotacion_anual']:5.2f} "
              f"costo S/{s['costo_total']:,.0f}{deg}")

    # Por pliegue y por tramo: es lo que sostiene "train y val son regímenes
    # opuestos" con números en vez de con una frase.
    for p in pliegues:
        for tramo in ("train", "val"):  # test NO se toca (D21)
            r, c = corre_baselines(panel, costos, sin_costo, p.rango(tramo))
            resumen_base[f"pliegue{p.idx}_{tramo}"] = r
            if p.idx == args.fold and tramo == "val":
                curvas_npz.update({f"val_f{p.idx}__{k}": v for k, v in c.items()})
    escribe_json("baselines.json", resumen_base)

    print("[5/6] banda nula (D10)")
    escribe_json("banda_nula.json", {
        "horizonte_completo": banda_nula(panel, costos, None),
        f"pliegue{args.fold}_val": banda_nula(panel, costos, pliegues[args.fold].rango("val")),
    })

    if args.sin_agente:
        # NO clobberar las curvas del agente. `--sin-agente` recalcula solo lo
        # barato, así que sobrescribir el .npz entero dejaba `agente.json` vivo
        # apuntando a curvas que ya no existían, y el notebook se caía con un
        # KeyError críptico. Se conservan las claves `agente_*` que ya estaban.
        ruta_npz = SALIDA / "curvas.npz"
        if ruta_npz.exists():
            with np.load(ruta_npz, allow_pickle=False) as viejo:
                previas = {k: viejo[k] for k in viejo.files if k.startswith("agente_")}
            if previas:
                print(f"   (se conservan {len(previas)} series del agente de la corrida anterior)")
                curvas_npz = {**previas, **curvas_npz}
        np.savez_compressed(ruta_npz, **curvas_npz)
        print(f"\nlisto (sin agente) en {(time.time()-t_inicio)/60:.1f} min")
        return

    print("[6/6] agente — piloto de D21 (el tramo de PRUEBA no se toca)")
    pliegue = pliegues[args.fold]
    print("   D22: rotación del ruido antes de entrenar")
    escribe_json("exploracion.json", rotacion_contra_log_std(panel, costos, pliegue.rango("val")))

    agente: dict[str, list[dict]] = {}
    for modo in ("logits", "delta"):
        agente[modo] = []
        for semilla in range(args.seeds):
            print(f"   entrenando modo={modo} semilla={semilla} ...", flush=True)
            s, curvas = entrena_y_evalua(panel, costos, pliegue, modo, semilla, args)
            agente[modo].append(s)
            for k, v in curvas.items():
                curvas_npz[f"agente_{modo}_s{semilla}__{k}"] = v
            print(f"      ret {s['retorno_total']:7.1%} | sharpe {s['sharpe']:6.2f} | "
                  f"maxDD {s['max_drawdown']:6.1%} | rot {s['rotacion_anual']:5.2f} | "
                  f"caja {s['peso_caja_medio']:5.1%} | {s['minutos_entrenamiento']:.1f} min")

    escribe_json("agente.json", {
        "config": {
            "vista": VISTA, "recompensa": args.reward, "algoritmo": "PPO",
            "net_arch": [64, 64], "timesteps": args.timesteps, "semillas": args.seeds,
            "log_std_init": args.log_std, "action_scale": args.action_scale,
            "pliegue": args.fold, "tramo_evaluado": "val",
            "advertencia": "PILOTO DE D21 — diagnóstico de plomería, NO hallazgos.",
        },
        "resultados": agente,
        "registro_D10": conteo(),
    })
    np.savez_compressed(SALIDA / "curvas.npz", **curvas_npz)
    print(f"   -> {SALIDA / 'curvas.npz'}")
    print(f"\nlisto en {(time.time()-t_inicio)/60:.1f} min")


if __name__ == "__main__":
    main()
