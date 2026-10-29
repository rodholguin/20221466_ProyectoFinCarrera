---
name: project-r8-sac-ddpg-corrida-20261011
description: "Ablación R8 con SAC/DDPG INCOMPLETA al 11-oct — DDPG 11/18 en el registro (sin commit), SAC 0/18; DDPG NO reproduce con la misma semilla; plan: retomado + servidor PUCP"
metadata:
  node_type: memory
  type: project
  originSessionId: 609d3520-e667-4530-a462-ebb7d78056c8
  modified: 2026-10-12T03:49:55.287Z
---

Ablación R8 (solo_mercado vs completa, 3 pliegues × 3 semillas × 150k, dsr, delta 0.05) con
SAC (`--sac-ent-coef 0.03`) y DDPG (`--ddpg-sigma 0.16`), un proceso por algo×vista con `--out` propio.

Estado al 2026-10-11 ~22:45 (laptop apagada por el autor):
- La corrida del 09-oct se BORRÓ a pedido del autor (21 líneas quitadas del registro con git checkout).
- DDPG relanzado el 11-oct: **11 corridas en `data/interim/registro_configuraciones.jsonl` SIN COMMIT**
  (solo_mercado pliegues 0-1 completos = 6/9; completa pliegue 0 + p1 s0,s1 = 5/9). JSON reconstruido
  desde el registro en `artefactos_oe1/ablacion_r8_ddpg_{vista}.parcial.json` (sin baselines/dims).
  Faltan: solo_mercado p2 s0-s2; completa p1 s2 + p2 s0-s2.
- SAC: detenido sin terminar ninguna corrida → 0 entradas; arranca de cero.

**Hallazgo: DDPG NO es determinista** — mismo panel (dataset_unificado 09-oct 10:22), misma config y
semilla dio otro resultado que el 09-oct (solo_mercado p0 s0: −11.0% vs −19.0%). Choca con G.4
(determinismo) del insumo de redacción. Verificar si a PPO le pasa lo mismo; probar torch.set_num_threads /
use_deterministic_algorithms con una corrida corta duplicada ANTES de la corrida definitiva.

**Why:** el script escribe el JSON solo al terminar las 9 corridas y no sabe retomar; se perdió trabajo 2 veces.
**How to apply:** antes de relanzar, implementar en `scripts/ablacion_r8.py` guardado por semilla + retomado
(saltar las (vista, pliegue, semilla) ya hechas, sin duplicar el registro). Ritmo medido en la laptop sin
batería: DDPG ~65-73 min/corrida con 2 procesos (SAC ~1.7x más lento). Servidor PUCP: ver [[project-r5-sentiment-status]];
el 11-oct `phantom` (172.19.4.64) no respondía; `bridge` entra a una máquina 'phantom' de 32 núcleos + 3 A5500
en 172.19.4.227 donde la llave de `rholguin` es rechazada — el autor lo resuelve con el administrador.
