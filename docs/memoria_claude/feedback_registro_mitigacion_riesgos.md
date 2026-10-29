---
name: feedback-registro-mitigacion-riesgos
description: "Al actualizar el registro de riesgos: añadir la mitigación aplicada, nunca podar el item que dejó de aplicar"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4d8057ad-f771-444f-9148-afcb5500f969
  modified: 2026-07-30T05:35:28.374Z
---

En el registro de riesgos del proyecto (`docs/riesgos_transversales_datos.txt` y
[[project-riesgos-datos-pendientes]]), cuando un riesgo deja de aplicar **NO se
borra ni se reescribe el item**: se le AÑADE qué mitigación se aplicó, con qué
evidencia, **qué parte sigue abierta** y **cuál es el límite de la mitigación**.

Corrección explícita del usuario (jul-2026): yo había reescrito dos items como
"quedó sin efecto" porque el cambio de universo los volvía inaplicables (el ancla
de MediaCloud para CORAREC1, los `pe_reliable=0` de SAGAC1). El usuario pidió lo
contrario: *"más que quitar lo que queda sin efecto, la cosa sería añadir lo que se
hizo para mitigar el riesgo"*.

**Why:** es un documento de tesis, no un backlog. El valor está en la trazabilidad:
el jurado/asesor tiene que poder ver qué riesgo se identificó, qué se hizo al
respecto y qué residuo queda. Un item borrado parece un riesgo que nunca existió, y
"sin efecto" suena a que se esquivó el problema en vez de haberlo atacado. Además,
un riesgo casi nunca se cierra del todo: el mecanismo suele seguir vivo para otros
activos (ruido temático) o el código de guarda sigue en el pipeline
(`_PE_ARTIFACT_PERIODS`).

**How to apply:** al tocar el registro, escribir `→ MITIGACIÓN (fecha): <qué se
hizo> / <evidencia o script> / LÍMITE: <qué no cubre> / SIGUE ABIERTO: <residuo>`.
Conservar las cifras y el texto original aunque hayan quedado desactualizados,
marcándolos como registro preliminar si las nuevas mediciones los reemplazan.
Aplica igual a las memorias del proyecto y a los docs de hallazgos R3-R6.
