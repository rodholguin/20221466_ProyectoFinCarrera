"""¿La query de MediaCloud se está perdiendo noticia que vive en las MARCAS?

EL PROBLEMA, DESCUBIERTO EN D17. `yape` son 607 titulares del corpus de BCP —el
SEGUNDO término más frecuente, por encima de `credicorp`— y NO ESTÁ EN LA QUERY.
Entraron de rebote: MediaCloud busca sobre el TEXTO COMPLETO, así que un
artículo sobre Yape cuyo cuerpo menciona al BCP entra igual. Pero si existe
noticia de Yape cuyo cuerpo NUNCA nombra al banco, hoy se pierde para siempre.
Lo mismo con Plaza Vea / Real Plaza / InkaFarma en InRetail, que son la cara
pública de la empresa.

QUÉ MIDE. Para cada marca, tres conteos sobre la colección Perú Nacional:
    (a) la marca sola
    (b) la query VIGENTE del activo
    (c) la marca Y NO la query vigente   <- LO QUE SE ESTÁ PERDIENDO
Si (c) es grande, hay que ampliar la query ANTES de la corrida definitiva, que
es el único momento en que sale barato.

POR QUÉ ES BARATO. `story_count` devuelve un ENTERO por llamada: no descarga
corpus, no pagina, no gasta LLM. Son ~30 llamadas en total.

OJO CON LEER DE MÁS: `story_count` cuenta ARTÍCULOS que mencionan el término en
cualquier parte del texto, no titulares que hablen de la marca. El número de (c)
es una COTA SUPERIOR de lo que se pierde, no una estimación de señal — la
relevancia real de ese material solo se sabría descargándolo y clasificándolo.
Sirve para decidir "vale la pena mirar" vs "es despreciable", nada más.

Uso:
  $env:MEDIACLOUD_API_TOKEN="..."
  python scripts/probe_mc_marcas.py
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TOKEN = os.environ.get("MEDIACLOUD_API_TOKEN", "")
if not TOKEN:
    raise SystemExit(
        "Define MEDIACLOUD_API_TOKEN antes de ejecutar.\n"
        "  PowerShell:  $env:MEDIACLOUD_API_TOKEN=\"...\"\n"
        "El token se rotó el 2026-08-18; el viejo quedó inerte en el historial.")

PERU_NATIONAL = 34412158
INICIO, FIN = dt.date(2012, 1, 1), dt.date(2025, 12, 31)

# Marcas a probar, por activo. Son las que D17 metió en el diccionario de la
# bandera `titular_nombra_empresa`. La query vigente se importa del propio
# módulo para que no se desincronicen.
#
# LAS MARCADAS [control] YA ESTÁN EN LA QUERY (`Plaza Vea` e `InkaFarma` en
# INRETC1). Se prueban a propósito: DEBEN dar ~0 en la columna "fuera de la
# query". Si dan otra cosa, el probe está mal y no hay que creerle al resto.
MARCAS = {
    "CREDITC1": ['"Yape"', '"Mibanco"', '"Krealo"', '"Prima AFP"',
                 '"Pacifico Seguros"'],
    "INRETC1":  ['"Plaza Vea"', '"InkaFarma"',          # [control]
                 '"Real Plaza"', '"Mifarma"', '"Vivanda"', '"Tiendas Mass"',
                 '"Quicorp"', '"Economax"'],
    "ALICORC1": ['"Intradevco"', '"Blanca Flor"', '"Don Vittorio"',
                 '"Sapolio"', '"Nicolini"'],
    "MINSURI1": ['"Mina Justa"', '"Marcobre"', '"Pucamarca"', '"Taboca"'],
    "FERREYC1": ['"Unimaq"', '"Motored"', '"Orvisa"'],
    "LUSURC1":  ['"Tecsur"'],
    "CPACASC1": ['"Fosfatos del Pacifico"'],
}


def main() -> None:
    import mediacloud.api as mc

    from src.sentiment.mediacloud_client import _build_query
    from src.universe import Config

    cfg = Config.load(ROOT / "config.yaml")
    queries = {a.bvl: _build_query(a) for a in cfg.assets}
    search = mc.SearchApi(TOKEN)

    def cuenta(q: str) -> int:
        for intento in range(4):
            try:
                r = search.story_count(q, start_date=INICIO, end_date=FIN,
                                       collection_ids=[PERU_NATIONAL])
                return r.get("relevant", 0) if isinstance(r, dict) else int(r)
            except Exception as e:
                if intento == 3:
                    print(f"    ERROR tras 4 intentos: {e}")
                    return -1
                time.sleep(5 * (intento + 1))
        return -1

    print("=" * 78)
    print("¿SE PIERDE NOTICIA DE MARCA? — Perú Nacional, 2012-2025")
    print("=" * 78)
    total_perdido = 0
    for tk, marcas in MARCAS.items():
        q_actual = queries.get(tk)
        if q_actual is None:
            continue
        n_actual = cuenta(q_actual)
        print(f"\n{tk}   query vigente = {n_actual:,} artículos")
        print(f"  {'marca':<18} {'sola':>9} {'FUERA de la query':>19} {'% que suma':>12}")
        for m in marcas:
            n_m = cuenta(m)
            n_fuera = cuenta(f"{m} AND NOT ({q_actual})")
            total_perdido += max(n_fuera, 0)
            pct = (n_fuera / n_actual) if n_actual > 0 else float("nan")
            alerta = "  <-- REVISAR" if n_actual > 0 and pct > 0.05 else ""
            print(f"  {m:<18} {n_m:>9,} {n_fuera:>19,} {pct:>11.1%}{alerta}")
            time.sleep(0.5)

    print("\n" + "=" * 78)
    print(f"TOTAL de artículos que las marcas traerían y hoy NO entran: "
          f"{total_perdido:,}")
    print("=" * 78)
    print("""
CÓMO DECIDIR CON ESTO:
  - Una marca con <5% adicional NO justifica re-descargar: el cuerpo del
    artículo ya la trae por mencionar al emisor.
  - Una marca con mucho volumen propio (Yape, Plaza Vea) hay que mirarla: puede
    ser noticia real de la empresa, pero también un río de marketing y de
    servicio al cliente ("¿cómo cambiar mi número en Yape?") que la taxonomía
    mandaría a magnitud 0 después de PAGAR el LLM.
  - REGLA DE ORO YA MEDIDA (taxonomía §7.2 y D17): la query maximiza RECALL; la
    precisión la resuelven el prefiltro y la taxonomía. Pero eso valía cuando el
    corpus era de 19.5k. Duplicarlo por marketing de una app no es lo mismo.
  - SI SE AMPLÍA LA QUERY hay que RE-DESCARGAR ese activo y anotar el cambio de
    versión de query en el parquet (la columna `query` ya se guarda), o las
    corridas dejan de ser comparables.
""")


if __name__ == "__main__":
    main()
