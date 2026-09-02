"""Volumen exacto de las queries de producción v2, ANTES de descargar.

Usa `story_count` (un entero por llamada, barato) con la MISMA query que usará
`fetch_stories`, para saber a qué corrida nos comprometemos. Estima además el
tiempo de LLM aplicando el ahorro medido del prefiltro.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mediacloud.api as mc

from src.universe import Config
from src.sentiment.mediacloud_client import _build_query

TOKEN = os.environ.get("MEDIACLOUD_API_TOKEN", "")
if not TOKEN:
    raise SystemExit("Define MEDIACLOUD_API_TOKEN")

SEG_POR_ARTICULO = float(os.environ.get("SEG_POR_ARTICULO", "47"))
AHORRO_PREFILTRO = 0.175      # medido sobre el corpus actual (§7.5)
RETENCION_ALLOWLIST = 0.35    # los 3 medios del allowlist sobre la colección

cfg = Config.load(ROOT / "config.yaml")
col = cfg.sources["sentiment"]["peru_national_collection_id"]
start = dt.date.fromisoformat(cfg.start)
end = dt.date.fromisoformat(cfg.end)
search = mc.SearchApi(TOKEN)

print(f"Colección {col} | {start} → {end}")
print(f"{'Activo':<10} {'colección':>10} {'~allowlist':>11} {'~tras pref.':>12} {'~horas LLM':>11}")
print("-" * 58)
tot_col = tot_llm = 0
for a in cfg.assets:
    q = _build_query(a)
    try:
        r = search.story_count(q, start_date=start, end_date=end,
                               collection_ids=[col])
        n = r.get("relevant", 0) if isinstance(r, dict) else int(r)
    except Exception as e:
        print(f"{a.bvl:<10} ERROR: {e}")
        continue
    n_allow = n * RETENCION_ALLOWLIST
    n_llm = n_allow * (1 - AHORRO_PREFILTRO)
    horas = n_llm * SEG_POR_ARTICULO / 3600
    tot_col += n
    tot_llm += n_llm
    print(f"{a.bvl:<10} {n:>10,} {n_allow:>11,.0f} {n_llm:>12,.0f} {horas:>11.1f}")

print("-" * 58)
print(f"{'TOTAL':<10} {tot_col:>10,} {'':>11} {tot_llm:>12,.0f} "
      f"{tot_llm*SEG_POR_ARTICULO/3600:>11.1f}")
print(f"\nA {SEG_POR_ARTICULO:.0f} s/artículo = "
      f"{tot_llm*SEG_POR_ARTICULO/3600/24:.1f} días continuos.")
for s in (5, 2, 1):
    print(f"  Si el servidor baja a {s} s/art: "
          f"{tot_llm*s/3600:.1f} h ({tot_llm*s/3600/24:.1f} días)")
print("\nNOTA: 'allowlist' y 'tras prefiltro' son ESTIMACIONES con las tasas")
print("medidas en el corpus viejo; el conteo de la colección sí es exacto.")
