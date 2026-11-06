---
name: project-d17-perimetro-bcp
description: "D17 (2026-08-30): perímetro BCP confirmado sin tocar la query; solo el 16.2% del corpus nombra a la empresa en el titular y ahí está el 83% del ruido con signo"
metadata: 
  node_type: memory
  type: project
  originSessionId: e9a825e5-240a-47f4-9395-4b226c9107f0
  modified: 2026-08-30T21:06:49.278Z
---

**D17 CERRADA el 2026-08-30.** Registro completo en `docs/decisiones_pendientes_OE1.txt` → D17.

**Parte 1 — el perímetro NO era el problema.** El activo es el BANCO (CREDITC1) y la
ventana de noticias es el GRUPO. **La query no cambia.** `Credicorp` son solo 505
titulares (5.0% del corpus de BCP, no el 51.4% que se le atribuía) y ahí vive noticia
material del banco (Helm Bank, sanción de Indecopi). BCP es ~97.7% de Credicorp. La parte
que de verdad no es BCP es `Credicorp Capital` (226), la mesa de análisis — la taxonomía
ya la manda a `mencion_incidental`. BAP sigue descartado como activo (se precia en NYSE).

**Parte 2 — el hallazgo real, y es de los 7 activos.** MediaCloud matchea sobre el
CUERPO, así que entra todo artículo que mencione al emisor en cualquier parte.
**Solo el 16.2% del corpus (3,162 de 19,528) nombra a la empresa en el TITULAR.**
Contra las 550 anotaciones (n=58 nombrados / 420 anónimos):
```
  estrato   relevancia humana   ponderada   precisión LLM v2.1
  NOMBRA          63.8%           44.0%           88.6%
  anónimo          2.1%            1.1%           16.7%
```
**El 83% de los falsos positivos y el 83% de la polaridad espuria salen del estrato
anónimo.** Es el resto del error que D11 atacó en julio y v2.1 no cerró.
Restringir conservaría el 80.4% de los eventos relevantes (83.5% de la masa).

**DECISIÓN: se MARCA, no se filtra.** R5 emite `titular_nombra_empresa` (regex
determinista, sin LLM), el LLM corre sobre el corpus completo, y la restricción se decide
en R6 como **brazo pre-registrado de la ablación de R8**. Mismo patrón que D11: la
decisión se mueve a donde es barato revertirla. Costo cero, sin re-descarga.

**Diccionario (incluye MARCAS, no solo razón social)** — está en D17 §DICCIONARIO.
Lo que hay que recordar:
- `ferreyros` ES UN APELLIDO: ~mitad de sus 74 titulares son personas, sobre todo el
  ex-ministro Eduardo Ferreyros. Lleva exclusión obligatoria.
- `inland energy` NO es Luz del Sur (es Majes II / Gobierno Regional de Arequipa).
- `yape` son 607 titulares —el 2º término más frecuente de BCP— y **no está en la query**;
  entraron de rebote. Pendiente barato: un `story_count` de MediaCloud para ver si se
  pierden titulares de Yape (y de Plaza Vea / Real Plaza / InkaFarma) cuyo cuerpo nunca
  nombra al emisor.
- Se incluyen las MATRICES (`credicorp`, `intercorp`): juicio del autor, reversible.

**Límite declarado:** n=58 en el estrato nombrado. El efecto es enorme (30x) pero los
intervalos son anchos; marcar en vez de filtrar es la mitigación de eso.

Ver [[project-r5-d16-piloto-rol]] y [[project-r5-evaluacion-integral]].
