# -*- coding: utf-8 -*-
"""R8 en paralelo: un proceso por (algoritmo, vista, pliegue, semilla).

POR QUÉ. `ablacion_r8.py` corre sus corridas una tras otra dentro de un
proceso. Medido el 2026-11-05 en la laptop de 16 núcleos lógicos: 12 procesos
de 1 hilo rinden ~7 veces lo que uno solo, y los pesos entrenados son
IDÉNTICOS con 1 u 8 hilos de torch, así que paralelizar no cambia ningún
número (scripts/verifica_determinismo.py).

CÓMO. Cada trabajo es una invocación de `ablacion_r8.py` acotada a una vista,
un pliegue y una semilla, con su propio JSON y su propio registro. Tres
garantías:
  * EL REGISTRO DE D10 LO ESCRIBE SOLO ESTE PROCESO. En Windows dos procesos
    que agregan líneas al mismo archivo a la vez pueden pisarse, y ese archivo
    es append-only y sostiene el Sharpe deflactado. Cada hijo anota en su
    registro propio; al terminar (bien o mal) el padre traslada sus líneas al
    registro real, una por una. Una corrida que se cayó después de evaluarse
    también se traslada: D10 cuenta lo que se miró, no lo que terminó.
  * RETOMA POR TRABAJO: un trabajo con su JSON completo no se repite. Cortar
    y relanzar el mismo comando sigue donde quedó.
  * AL FINAL junta los trabajos en `ablacion_r8_{algo}.json`, con el mismo
    formato que `ablacion_r8.py`, y exige que todos usen el mismo panel y la
    misma versión del simulador.

Uso:
    python scripts/lanza_r8.py --ddpg-sigma <cal> --sac-ent-coef <cal>
    python scripts/lanza_r8.py --algos ppo --procesos 12
    python scripts/lanza_r8.py --algos ddpg --vistas-offpolicy solo_mercado completa
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.env.features import VISTAS_ABLACION  # noqa: E402
from src.env.registro import REGISTRO  # noqa: E402

DIR_DEFECTO = Path("data/interim/artefactos_oe1/r8_paralelo")
#: Costo relativo aproximado por corrida (medido, 150k pasos): para lanzar
#: primero lo más largo y que el último proceso no quede solo al final.
PESO = {"sac": 13.0, "ddpg": 9.5, "ppo": 0.8}


def trabajos(args) -> list[dict]:
    out = []
    for algo in args.algos:
        vistas = args.vistas_ppo if algo == "ppo" else args.vistas_offpolicy
        for vista in vistas:
            for f in range(args.folds):
                for s in range(args.seeds):
                    nombre = f"{algo}_{vista}_p{f}_s{s}"
                    out.append({
                        "algo": algo, "vista": vista, "pliegue": f, "semilla": s,
                        "nombre": nombre,
                        "json": args.dir / "trabajos" / f"{nombre}.json",
                        "registro": args.dir / "trabajos" / f"{nombre}.registro.jsonl",
                        "log": args.dir / "trabajos" / f"{nombre}.log",
                    })
    # lo más caro primero; `completa` (más dimensiones) antes que las otras
    return sorted(out, key=lambda t: (-PESO[t["algo"]], t["vista"] != "completa"))


def terminado(t: dict) -> bool:
    if not t["json"].exists():
        return False
    d = json.loads(t["json"].read_text(encoding="utf-8"))
    filas = d.get("vistas", {}).get(t["vista"], {}).get(f"pliegue{t['pliegue']}", [])
    return not d.get("parcial", True) and any(r.get("seed") == t["semilla"] for r in filas)


def comando(t: dict, args) -> list[str]:
    cmd = [sys.executable, "-X", "utf8", str(RAIZ / "scripts" / "ablacion_r8.py"),
           "--algo", t["algo"], "--views", t["vista"],
           "--pliegues", str(t["pliegue"]), "--seed-list", str(t["semilla"]),
           "--folds", str(args.folds), "--seeds", str(args.seeds),
           "--timesteps", str(args.timesteps), "--reward", args.reward,
           "--out", str(t["json"]), "--registro", str(t["registro"]),
           "--hilos", "1", "--sin-tablas"]
    if t["algo"] == "ppo":
        cmd += ["--log-std", str(args.log_std)]
    elif t["algo"] == "sac":
        cmd += ["--sac-ent-coef", str(args.sac_ent_coef)]
    else:
        cmd += ["--ddpg-sigma", str(args.ddpg_sigma)]
    return cmd


def traslada_registro(t: dict, registro: Path) -> int:
    """Pasa las líneas del registro del hijo al registro real. Un solo escritor."""
    if not t["registro"].exists():
        return 0
    lineas = [ln for ln in t["registro"].read_text(encoding="utf-8").splitlines() if ln.strip()]
    if lineas:
        registro.parent.mkdir(parents=True, exist_ok=True)
        with registro.open("a", encoding="utf-8") as fh:
            for ln in lineas:
                json.loads(ln)  # se cae antes de escribir basura
                fh.write(ln + "\n")
    t["registro"].unlink()
    return len(lineas)


def combina(jsons: list[dict]) -> dict:
    """Junta trabajos de UN algoritmo en el formato de ablacion_r8.py."""
    if not jsons:
        raise ValueError("no hay trabajos que combinar")
    for clave in ("simulador", "panel_sha256"):
        valores = {d.get(clave) for d in jsons}
        if len(valores) != 1:
            raise ValueError(f"los trabajos no comparten {clave}: {sorted(map(str, valores))}")
    algos = {d["config"]["algo"] for d in jsons}
    if len(algos) != 1:
        raise ValueError(f"combina() es por algoritmo; llegaron {sorted(algos)}")
    out = {"config": dict(jsons[0]["config"]), "vistas": {}, "baselines": {}, "dims": {},
           "simulador": jsons[0]["simulador"], "panel_sha256": jsons[0]["panel_sha256"]}
    for d in jsons:
        out["dims"].update(d.get("dims", {}))
        out["baselines"].update(d.get("baselines", {}))
        for vista, pliegues in d.get("vistas", {}).items():
            for pl, filas in pliegues.items():
                actual = {r["seed"]: r for r in out["vistas"].setdefault(vista, {}).get(pl, [])}
                for r in filas:
                    if r["seed"] in actual and actual[r["seed"]] != r:
                        raise ValueError(f"{vista} {pl} semilla {r['seed']} aparece dos veces con otro valor")
                    actual[r["seed"]] = r
                out["vistas"][vista][pl] = [actual[k] for k in sorted(actual)]
    out["config"]["views"] = sorted(out["vistas"])
    for k in ("out", "registro", "pliegues", "seed_list", "retoma"):
        out["config"].pop(k, None)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--algos", nargs="+", default=["ppo", "ddpg", "sac"], choices=["ppo", "ddpg", "sac"])
    ap.add_argument("--vistas-ppo", nargs="+", default=list(VISTAS_ABLACION) + ["completa"])
    ap.add_argument("--vistas-offpolicy", nargs="+", default=["solo_mercado", "completa"])
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--timesteps", type=int, default=150_000)
    ap.add_argument("--reward", default="dsr")
    ap.add_argument("--log-std", type=float, default=-2.0)
    ap.add_argument("--sac-ent-coef", type=float, default=None)
    ap.add_argument("--ddpg-sigma", type=float, default=None)
    ap.add_argument("--procesos", type=int, default=12)
    ap.add_argument("--dir", type=Path, default=DIR_DEFECTO)
    ap.add_argument("--registro", type=Path, default=REGISTRO, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if "sac" in args.algos and args.sac_ent_coef is None:
        ap.error("SAC necesita --sac-ent-coef (calibrado por rotación, ver calibra_exploracion_r7.py)")
    if "ddpg" in args.algos and args.ddpg_sigma is None:
        ap.error("DDPG necesita --ddpg-sigma (calibrado por rotación, ver calibra_exploracion_r7.py)")
    (args.dir / "trabajos").mkdir(parents=True, exist_ok=True)

    todos = trabajos(args)
    pendientes = [t for t in todos if not terminado(t)]
    # restos de una corrida anterior cortada: sus líneas se trasladan YA
    for t in todos:
        traslada_registro(t, args.registro)
    carga = sum(PESO[t["algo"]] for t in pendientes)
    print(f"{len(todos)} trabajos · {len(todos) - len(pendientes)} ya hechos · {len(pendientes)} por correr "
          f"· {args.procesos} procesos · ~{carga / min(args.procesos, max(len(pendientes), 1)):.0f} min si escala lineal")

    entorno = {**os.environ, "PYTHONPATH": str(RAIZ), "PYTHONIOENCODING": "utf-8",
               "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    corriendo: list[tuple[dict, subprocess.Popen, object]] = []
    fallidos, hechos, t0 = [], 0, time.time()
    while pendientes or corriendo:
        while pendientes and len(corriendo) < args.procesos:
            t = pendientes.pop(0)
            log = t["log"].open("w", encoding="utf-8")
            pr = subprocess.Popen(comando(t, args), cwd=RAIZ, env=entorno, stdout=log, stderr=subprocess.STDOUT)
            corriendo.append((t, pr, log))
        time.sleep(2)
        for item in list(corriendo):
            t, pr, log = item
            if pr.poll() is None:
                continue
            log.close()
            corriendo.remove(item)
            n = traslada_registro(t, args.registro)
            if pr.returncode == 0 and terminado(t):
                hechos += 1
            else:
                fallidos.append(t["nombre"])
            print(f"[{(time.time() - t0) / 60:5.1f} min] {'ok ' if pr.returncode == 0 else 'ERR'} "
                  f"{t['nombre']} (registro +{n}) · faltan {len(pendientes) + len(corriendo)}", flush=True)

    for algo in args.algos:
        jsons = [json.loads(t["json"].read_text(encoding="utf-8"))
                 for t in todos if t["algo"] == algo and terminado(t)]
        if not jsons:
            continue
        r = combina(jsons)
        esperados = sum(1 for t in todos if t["algo"] == algo)
        r["parcial"] = len(jsons) < esperados
        destino = args.dir / f"ablacion_r8_{algo}.json"
        destino.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{algo}: {len(jsons)}/{esperados} trabajos -> {destino}")
    if fallidos:
        print(f"\nFALLARON {len(fallidos)}: {', '.join(fallidos)} (ver sus .log; relanzar retoma)")
        sys.exit(1)


if __name__ == "__main__":
    main()
