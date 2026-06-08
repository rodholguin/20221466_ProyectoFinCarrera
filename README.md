# Pipeline de extracción de datos — OE2 (R3–R6)

Andamiaje para el **Objetivo Específico 2** de la tesis de DRL aplicado a la BVL:
construir un dataset unificado (mercado + fundamentales + sentimiento) para un
universo de 5 activos, periodo **2005–2025**.

## Universo (cerrado)

| Sector | Empresa | BVL | Yahoo (respaldo) | Entidad EEFF (SMV) |
|---|---|---|---|---|
| Banca | Credicorp | `BAP` | `BAP` (NYSE, USD) | BCP — *ver nota* |
| Minero | Buenaventura | `BUENAVC1` | `BVN` (NYSE) | Cía. de Minas Buenaventura |
| Alimentos | Alicorp | `ALICORC1` | `ALICORC1.LM`¹ | Alicorp S.A.A. |
| Retail | Saga Falabella | `SAGAC1` | `SAGAC1.LM`¹ | Saga Falabella S.A. |
| Manufactura | Aceros Arequipa | `CORAREC1` | `CORAREC1.LM`¹ | Corp. Aceros Arequipa S.A. |

¹ Verificar el ticker de Yahoo uno por uno: para acciones solo-BVL la cobertura
es irregular. Por eso la BVL es la fuente **primaria** y Yahoo el respaldo.

**Nota banca (Credicorp):** es el activo más complejo para fundamentales. Reporta
con taxonomía de banco y en USD a nivel holding (Bermudas). Para R4 conviene usar
los EEFF de **BCP** en la SMV o los consolidados de Credicorp Ltd, y tratar la
moneda aparte. (El usuario optó por mantenerlo y asumir el trabajo extra.)

## Decisión de fuentes

- **Mercado (R3):** BVL primaria + Yahoo fallback, con reconciliación de cierres.
- **Fundamentales (R4):** **SMV web service = la más segura** (regulador estatal,
  presentación legal obligatoria, datos abiertos, estructurado). BVL `dataondemand`
  (endpoint que ya usó la maestría de Ancajima) como secundaria y validación cruzada.
- **Sentimiento (R5):** Media Cloud API v4. `story_list` exige `collection_ids` o
  `sources`; se resuelve el id de la colección nacional de Perú con el DirectoryApi.

## Estructura

```
config.yaml                         # universo, fechas, fuentes, rutas
requirements.txt
src/
  universe.py                       # carga config + esquemas canónicos
  market/
    market_client.py                # R3: BVL (primaria) + Yahoo (fallback)
    technical_indicators.py         # R3 (2.2): SMA/EMA/MACD/RSI/vol
  fundamentals/
    fundamentals_client.py          # R4: SMV (primaria) + BVL dataondemand
  sentiment/
    mediacloud_client.py            # R5 (2.6): noticias + colección Perú
    llm_sentiment.py                # R5 (2.7): clasificación + score diario
  integration/
    build_dataset.py                # R6: panel unificado + vistas de R8
data/{raw,interim,processed}
```

## Plan de acción (pasos a seguir)

### Paso 0 — Setup
1. `pip install -r requirements.txt`
2. `export MEDIACLOUD_API_TOKEN=...` (y la API key del LLM elegido)
3. `python -m src.universe` para verificar el universo.

### R3 — Mercado
4. Capturar el endpoint real de cotizaciones de la BVL (DevTools > Network, o
   probar la familia `dataondemand/v1`) y completar `_BVL_QUOTES_ENDPOINT` y el
   parseo en `market_client.py`.
5. Verificar tickers de Yahoo (`.LM`) activo por activo.
6. Correr `market_client.py`; revisar el reporte de reconciliación BVL↔Yahoo.
7. Aplicar `technical_indicators.add_indicators`. **V&V (2.3):** faltantes y
   calendario de días hábiles de la BVL (feriados PE).

### R4 — Fundamentales (empezar por SMV)
8. `python -m src.fundamentals.fundamentals_client` para listar las operaciones
   del WSDL de la SMV y mapear nombres/parámetros reales.
9. Implementar el bucle trimestral en `fetch_smv` (situación financiera, resultados).
10. Pedir a tu asesor el repo de la maestría para replicar el payload de
    `dataondemand/financialstatements/` (fuente secundaria) y validar cruzado.
11. Resolver el diccionario ticker ↔ entidad SMV (validación manual). **BCP** para banca.
12. Implementar `compute_ratios` (P/E, ROE, DY): homogeneizar moneda (cuentas en
    miles, soles/dólares) y fijar la convención trailing. Usar `known_date` (fecha
    de presentación) para evitar look-ahead. **V&V (2.5):** muestra validada a mano.
    Asumir huecos 2005–2007 → forward-fill/interpolación documentada.

### R5 — Sentimiento
13. `python -m src.sentiment.mediacloud_client` → copiar el id de la colección
    nacional de Perú a `config.yaml`. (Alternativa más precisa: acotar con `sources`.)
14. `fetch_stories` por emisor; ajustar los alias de `_build_query`.
15. Conectar el proveedor LLM en `llm_sentiment.classify_article` (zero-shot, JSON,
    caché). Agregar a score diario. **V&V (2.8):** muestra etiquetada a mano, F1.

### R6 — Dataset unificado
16. `build_unified(...)` sobre el calendario de la BVL. Sentimiento 0 donde no hay
    noticias; fundamentales con `merge_asof` (forward-fill desde `known_date`).
17. `feature_views(...)` entrega las 4 configuraciones de señales de R8.
18. **V&V (2.10):** diccionario de datos + estadísticas; guardar en Parquet.

## Limitaciones de este andamiaje
- Las llamadas a BVL/SMV/Media Cloud/LLM **no se pueden probar offline**; los
  módulos traen el patrón de llamada correcto y `TODO`s donde hace falta el
  contrato real (endpoint/payload/WSDL) o un token. Ejecutar en local con red.
- El `config.yaml` carga y los módulos sin red (indicadores, integración) están
  probados con datos sintéticos.
