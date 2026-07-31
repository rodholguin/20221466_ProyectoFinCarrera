"""¿El EEFF INDIVIDUAL de InRetail "adelanta" lo que dirá el CONSOLIDADO?

Motivación (riesgos §3(a.4)): en INRETC1 la Información Financiera Intermedia
CONSOLIDADA se divulga 9-19 días DESPUÉS de la individual (30/30 trimestres). El
pipeline consume el consolidado (smv_tipo="C") y, tras el fix, lo fecha con el
hecho de la consolidada. Pregunta abierta del usuario: si la individual sale
antes y estuviera correlacionada con la consolidada, el mercado ya habría
conocido la señal 2 semanas antes -> la fecha conservadora nos costaría
información (y la anterior no sería tan "look-ahead").

Este probe mide la relación con datos reales del SMV (obtener_InfoFinanciera,
1 llamada por período y tipo, cacheada en data/raw/smv_cache):
  - Utilidad neta TRIMESTRAL individual vs consolidada: correlación en niveles y
    en cambios trimestrales, coincidencia de SIGNO y magnitud relativa.
  - Patrimonio y activo: si el individual llevara las subsidiarias por método de
    participación, su patrimonio seguiría al consolidado (aunque su P&L no).

Uso:  python scripts/probe_inretail_i_vs_c.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.universe import Config
from src.fundamentals.fundamentals_client import (
    _fetch_period_raw, _quarter_periods, _rows_for_asset,
)

FIELDS = ("UtilidadNeta", "PatrimonioTotal", "ActivoTotal", "TotalIngreso")
START, END = "2012-10-01", "2025-12-31"   # IPO de InRetail: oct-2012


def _serie(client, asset, periods, tipo: str, cache) -> pd.DataFrame:
    """DataFrame [period x FIELDS] del resumen InfoFinanciera para un tipo."""
    rows = {}
    for year, q in periods:
        try:
            raw = _fetch_period_raw(client, "obtener_InfoFinanciera", year, q, tipo, cache)
        except Exception as exc:
            print(f"  {year}Q{q} {tipo}: {exc}")
            continue
        found = _rows_for_asset(raw, asset)
        if not found:
            continue
        r = found[0]
        rows[f"{year}Q{q}"] = {f: pd.to_numeric(r.get(f), errors="coerce") for f in FIELDS}
    return pd.DataFrame(rows).T.sort_index()


def main() -> None:
    from zeep import Client

    cfg = Config.load(ROOT / "config.yaml")
    cache = ROOT / cfg.paths["raw"] / "smv_cache"
    asset = [a for a in cfg.assets if a.bvl == "INRETC1"][0]
    periods = _quarter_periods(START, END)

    client = Client(cfg.sources["fundamentals"]["smv_wsdl"])
    ind = _serie(client, asset, periods, "I", cache)
    con = _serie(client, asset, periods, "C", cache)
    print(f"períodos individual={len(ind)} consolidado={len(con)}")

    comunes = sorted(set(ind.index) & set(con.index))
    ind, con = ind.loc[comunes], con.loc[comunes]
    print(f"períodos comparables: {len(comunes)} ({comunes[0]} .. {comunes[-1]})\n")

    for f in FIELDS:
        i, c = ind[f].astype(float), con[f].astype(float)
        ok = i.notna() & c.notna()
        if ok.sum() < 8:
            print(f"{f}: datos insuficientes ({int(ok.sum())})")
            continue
        i, c = i[ok], c[ok]
        print(f"--- {f} (miles S/, n={len(i)}) ---")
        print(f"  individual : media {i.mean():>12,.0f}  min {i.min():>12,.0f}  max {i.max():>12,.0f}")
        print(f"  consolidado: media {c.mean():>12,.0f}  min {c.min():>12,.0f}  max {c.max():>12,.0f}")
        print(f"  ratio ind/con (mediana): {(i / c).median():.3f}")
        print(f"  corr NIVELES   Pearson {i.corr(c):+.3f}  Spearman {i.corr(c, method='spearman'):+.3f}")
        di, dc = i.diff().dropna(), c.diff().dropna()
        j = di.index.intersection(dc.index)
        print(f"  corr CAMBIOS   Pearson {di[j].corr(dc[j]):+.3f}  "
              f"Spearman {di[j].corr(dc[j], method='spearman'):+.3f}")
        if f == "UtilidadNeta":
            same = (i > 0) == (c > 0)
            print(f"  mismo SIGNO: {int(same.sum())}/{len(same)} trimestres  "
                  f"(individual>0 en {int((i > 0).sum())}, consolidado>0 en {int((c > 0).sum())})")
            same_dir = (di[j] > 0) == (dc[j] > 0)
            print(f"  misma DIRECCIÓN del cambio: {int(same_dir.sum())}/{len(same_dir)} "
                  f"({same_dir.mean():.0%}; azar = 50%)")
        print()

    out = ROOT / "data" / "interim" / "probe_inretail_i_vs_c.csv"
    pd.concat({"individual": ind, "consolidado": con}, axis=1).to_csv(out)
    print("detalle por trimestre ->", out)


if __name__ == "__main__":
    main()
