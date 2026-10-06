"""OE1 — contador de configuraciones entrenadas (D10).

El Sharpe deflactado de Bailey y López de Prado corrige por el NÚMERO DE
CONFIGURACIONES PROBADAS. El compromiso escrito en D10 es llevar ese contador
desde la PRIMERA corrida: contarlas al final no es honesto, porque nadie
recuerda los intentos que salieron mal.

Esto es un archivo append-only. No se edita, no se compacta, no se limpia. Si
una corrida se abandona a los dos minutos, igual cuenta: el sesgo de selección
lo produce haberla mirado, no haberla terminado.

Cada línea registra QUÉ se entrenó y SOBRE QUÉ TRAMO. El campo `tramo` es el que
permite defender el piloto de D21: mientras diga `val`, el tramo de prueba sigue
virgen y estas corridas no contaminan la evaluación final.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REGISTRO = Path("data/interim/registro_configuraciones.jsonl")


def hash_config(config: dict[str, Any]) -> str:
    """Huella estable de una configuración (mismo dict -> mismo hash)."""
    crudo = json.dumps(config, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(crudo).hexdigest()[:12]


def registra(
    config: dict[str, Any],
    tramo: str,
    resultado: dict[str, Any] | None = None,
    ruta: Path | str = REGISTRO,
) -> str:
    """Anota una corrida y devuelve su huella.

    Args:
        config: todo lo que define el experimento (vista, recompensa, semilla,
            pliegue, costos, hiperparámetros).
        tramo: 'train', 'val' o 'test'. Ver la nota sobre D21 arriba.
        resultado: métricas, si ya se tienen.
    """
    if tramo not in {"train", "val", "test"}:
        raise ValueError(f"tramo inválido: {tramo!r}")
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    huella = hash_config(config)
    linea = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hash": huella,
        "tramo": tramo,
        "config": config,
        "resultado": resultado or {},
    }
    with ruta.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(linea, ensure_ascii=False, default=str) + "\n")
    return huella


def conteo(ruta: Path | str = REGISTRO) -> dict[str, int]:
    """Cuántas corridas y cuántas configuraciones DISTINTAS se han probado.

    Lo que entra al Sharpe deflactado es `configuraciones_distintas`: repetir la
    misma configuración con otra semilla no es una prueba nueva de estrategia,
    es una réplica de la misma. Se reportan ambos porque la distinción hay que
    poder defenderla.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        return {"corridas": 0, "configuraciones_distintas": 0, "con_test": 0}
    huellas: set[str] = set()
    estrategias: set[str] = set()
    corridas = con_test = 0
    with ruta.open(encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            fila = json.loads(linea)
            corridas += 1
            huellas.add(fila["hash"])
            cfg = dict(fila.get("config", {}))
            cfg.pop("seed", None)  # la semilla no define una estrategia distinta
            estrategias.add(hash_config(cfg))
            if fila.get("tramo") == "test":
                con_test += 1
    return {
        "corridas": corridas,
        "configuraciones_distintas": len(estrategias),
        "hashes_distintos": len(huellas),
        "con_test": con_test,
    }
