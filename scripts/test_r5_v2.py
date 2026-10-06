"""Prueba rápida de los módulos nuevos de R5 v2 (sin llamar al LLM)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.sentiment.taxonomia import TAXONOMIA, prefiltro, normaliza
from src.sentiment.llm_sentiment import PROMPT_VERSION, _parse, aggregate_daily
from src.sentiment.mediacloud_client import _build_query, deduplicar
from src.universe import Config, SENTIMENT_SCHEMA

print(f"imports OK | prompt {PROMPT_VERSION} | {len(TAXONOMIA)} categorias\n")

print("PREFILTRO")
casos = [
    "BVL cierra en alza apoyada por acciones mineras",
    "BCP patrocina torneo de futbol escolar",
    "Minsur, segundo productor mundial de estano, eleva produccion",   # NO debe caer
    "Banco Mundial recorta proyeccion de crecimiento para Peru",       # NO debe caer
    "Alicorp firma acuerdo para comprar el 60% de Inka Crops",         # NO debe caer
    "Teleton Peru celebro a las empresas que ayudaron",
]
for t in casos:
    print(f"  {prefiltro(t):<20} <- {t[:60]}")

print("\nNORMALIZA (fuerza polaridad solo si magnitud > 0)")
for cat, pol in [("patrocinio_rse", "positivo"), ("indice_bursatil", "negativo"),
                 ("resultados", "positivo"), ("sector_macro", "negativo"),
                 ("categoria_inventada", "positivo"), ("resultados", "basura")]:
    print(f"  {str((cat, pol)):<40} -> {normaliza(cat, pol)}")

print("\nPARSEO")
pruebas = [
    '{"categoria":"resultados","polaridad":"positivo"}',
    '```json\n{"categoria":"indice_bursatil","polaridad":"no_aplica"}\n```',
    'Claro, aqui tienes: {"categoria":"operacional","polaridad":"neutral"}',
    'lo siento, no puedo clasificar esto',
    '{"categoria":"no_existe","polaridad":"positivo"}',
]
for p in pruebas:
    print(f"  {_parse(p)}   <- {p[:52]!r}")

print("\nQUERIES DEL UNIVERSO VIGENTE")
cfg = Config.load(ROOT / "config.yaml")
for a in cfg.assets:
    print(f"  {a.bvl:<10} {_build_query(a)}")

print("\nDEDUPLICACION (ventana 2 dias)")
d = pd.DataFrame({
    "title": ["Alicorp compra Inka Crops", "Alicorp compra Inka Crops",
              "Alicorp compra Inka Crops", "Otra noticia"],
    "publish_date": ["2024-03-01", "2024-03-02", "2024-03-20", "2024-03-01"],
    "url": ["u1", "u2", "u3", "u4"],
})
print(f"  entrada {len(d)} -> salida {len(deduplicar(d))} "
      f"(debe quedar 3: se cae solo el del dia siguiente)")

print("\nAGREGACION DIARIA")
art = pd.DataFrame({
    "id": ["a", "b", "c", "d"],
    "ticker": ["ALICORC1"] * 4,
    "publish_date": ["2024-03-01"] * 4,
    "title": ["t1", "t2", "t3", "t4"],
    "categoria": ["resultados", "crisis_evento_adverso", "indice_bursatil",
                  "operacional"],
    "polaridad": ["positivo", "negativo", None, "positivo"],
    "magnitud": [1.0, 1.0, 0.0, 0.6],
    "relevante": [1, 1, 0, 1],
    "origen": ["llm"] * 4,
})
daily = aggregate_daily(art)
print(daily[SENTIMENT_SCHEMA].to_string(index=False))
# D15 (2026-09-01): la magnitud dejó de ser multiplicador y `mag_pos`/`mag_neg`
# se reemplazaron por CONTEOS por celda tramo x polaridad. La propiedad que este
# test verifica no cambió —una buena y una mala el mismo día NO se cancelan,
# porque viven en columnas distintas— solo se expresa con conteos.
pos = int(daily.n_alto_pos.iloc[0] + daily.n_resto_pos.iloc[0])
neg = int(daily.n_alto_neg.iloc[0] + daily.n_resto_neg.iloc[0])
print("\n  Buena + mala el mismo dia: los conteos NO se cancelan ->",
      f"pos={pos}, neg={neg}")
assert pos > 0 and neg > 0, "los conteos por signo se cancelaron: D15 mal implementada"
print("  Esquema completo:", list(daily.columns) == SENTIMENT_SCHEMA or "ver arriba")
