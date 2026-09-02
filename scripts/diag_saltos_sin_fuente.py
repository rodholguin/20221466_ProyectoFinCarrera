"""Los saltos de precio SIN fuente atribuible: ¿por qué ocurren?

De los 594 saltos (|z|>=3) que mide scripts/diag_saltos_vs_fuentes.py, el 25% no
tiene NI hecho de importancia NI noticia en la ventana T-3..T. Este script los
aísla y descarta, en orden, las explicaciones MECÁNICAS antes de salir a buscar
explicaciones de mercado:

  (a) MOVIMIENTO COMÚN. Si varios activos saltan el mismo día, no es un evento de
      la empresa: es mercado (macro, índice, flujo). No hace falta ninguna fuente
      idiosincrática y no es una falla del canal de eventos.
  (b) EX-DIVIDENDO. Una caída el día ex-div es mecánica. close_total_return
      debería absorberla; si aparece, hay un bug en R3.
  (c) PRECIO STALE / ILIQUIDEZ. Un precio congelado seguido de puesta al día
      produce un salto falso. Es el problema de D8 (is_no_trade).
  (d) CALENDARIO. Fin de mes/trimestre y meses de revisión de índices
      (MSCI/FTSE revisan en feb/may/ago/nov) concentran flujo sin noticia.

Lo que sobreviva a las cuatro es el residuo genuino: candidatos a que haya una
FUENTE QUE NO ESTAMOS CONSIDERANDO.

Uso:
  python scripts/diag_saltos_sin_fuente.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
CACHE = RAW / "smv_cache"

RPJ = {"CREDITC1": "B80005", "MINSURI1": "A20032", "ALICORC1": "B30006",
       "INRETC1": "OE5087", "CPACASC1": "CD0005", "FERREYC1": "B60001",
       "LUSURC1": "B40008"}
HORA_CORTE, VENTANA, UMBRAL = 16, 3, 3.0


def hechos_fechas(tic: str) -> np.ndarray:
    f = CACHE / f"bvl_hechos_{RPJ[tic]}_2012_2025.json"
    out = []
    for x in json.loads(f.read_text(encoding="utf-8")):
        ts = pd.to_datetime(str(x.get("registerDate")), errors="coerce")
        if pd.isna(ts):
            continue
        out.append(ts.normalize()
                   + pd.Timedelta(days=1 if ts.hour >= HORA_CORTE else 0))
    return pd.DatetimeIndex(out).values


def noticias_fechas(tic: str) -> np.ndarray:
    f = RAW / f"news_{tic}.parquet"
    if not f.exists():
        return np.array([], dtype="datetime64[ns]")
    d = pd.read_parquet(f)
    return (pd.to_datetime(d["publish_date"], errors="coerce")
            .dt.normalize().dropna().values)


def mercado(tic: str) -> pd.DataFrame:
    d = pd.read_parquet(INTERIM / f"market_{tic}.parquet")
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    s = d["close_total_return"].astype(float)
    r = s.pct_change()
    raw = (d["close_raw"].astype(float).pct_change()
           if "close_raw" in d.columns else r)
    o = pd.DataFrame({"ret": r, "ret_raw": raw})
    o["vol"] = r.shift(1).rolling(60, min_periods=30).std()
    o["z"] = o.ret / o.vol
    cero = (o.ret.abs() < 1e-9).astype(int)
    o["stale_prev"] = cero.shift(1).rolling(5).sum()
    return o.dropna(subset=["z"])


def main() -> None:
    V = pd.Timedelta(days=VENTANA)
    todos, mkt = [], {}
    for tic in RPJ:
        m = mercado(tic)
        mkt[tic] = m
        hs, ns = hechos_fechas(tic), noticias_fechas(tic)
        s = m[(m.z.abs() >= UMBRAL) & (m.ret.abs() > 1e-9)
              & (m.stale_prev.fillna(0) < 3)]
        for t, row in s.iterrows():
            def hay(a, _t=t):
                return bool(((a >= np.datetime64(_t - V))
                             & (a <= np.datetime64(_t))).any())
            todos.append({"tic": tic, "fecha": t, "ret": row.ret, "z": row.z,
                          "ret_raw": row.ret_raw, "stale_prev": row.stale_prev,
                          "hecho": hay(hs), "noticia": hay(ns)})
    d = pd.DataFrame(todos)
    sf = d[~d.hecho & ~d.noticia].copy()
    con = d[d.hecho | d.noticia].copy()
    print("=" * 78)
    print(f"SALTOS SIN FUENTE ATRIBUIBLE: {len(sf)} de {len(d)} ({len(sf)/len(d):.0%})")
    print("=" * 78)
    print(sf.groupby("tic").size().to_string())

    print("\n" + "=" * 78)
    print("(a) ¿ES MOVIMIENTO COMÚN? — cuántos ACTIVOS se mueven fuerte el mismo día")
    print("=" * 78)
    z = pd.DataFrame({t: mkt[t].z for t in RPJ})
    fuertes = (z.abs() >= 2).sum(axis=1)
    sf["n_fuertes"] = sf.fecha.map(fuertes).fillna(0).astype(int)
    con["n_fuertes"] = con.fecha.map(fuertes).fillna(0).astype(int)
    print(f"  {'':30}{'sin fuente':>12}{'con fuente':>12}")
    for k in (2, 3, 4):
        print(f"  >= {k} activos con |z|>=2 a la vez{(sf.n_fuertes >= k).mean():12.0%}"
              f"{(con.n_fuertes >= k).mean():12.0%}")
    print(f"  {'mediana de activos fuertes':30}{sf.n_fuertes.median():12.0f}"
          f"{con.n_fuertes.median():12.0f}")

    print("\n" + "=" * 78)
    print("(b) ¿EX-DIVIDENDO? — el retorno total no debería mostrarlo")
    print("=" * 78)
    n_aj = int(((sf.ret - sf.ret_raw).abs() > 1e-6).sum())
    print(f"  saltos sin fuente donde ret_total != ret_crudo: {n_aj} de {len(sf)}")
    print("  (0 = ninguno viene de un ajuste por dividendo o split)")

    print("\n" + "=" * 78)
    print("(c) ¿ILIQUIDEZ? — sesiones con precio congelado en los 5 días previos")
    print("=" * 78)
    print(f"  {'':24}{'sin fuente':>12}{'con fuente':>12}")
    print(f"  {'media de días stale':24}{sf.stale_prev.mean():12.2f}"
          f"{con.stale_prev.mean():12.2f}")
    print(f"  {'% con >=1 día stale':24}{(sf.stale_prev >= 1).mean():12.0%}"
          f"{(con.stale_prev >= 1).mean():12.0%}")

    print("\n" + "=" * 78)
    print("(d) ¿CALENDARIO? — fin de mes y meses de revisión de índices")
    print("=" * 78)
    for nom, s in (("sin fuente", sf), ("con fuente", con)):
        dia, mes = s.fecha.dt.day, s.fecha.dt.month
        print(f"  {nom:<12} fin de mes {((dia >= 26) | (dia <= 3)).mean():5.0%}"
              f"   (esperado ~27%)   feb/may/ago/nov {mes.isin([2,5,8,11]).mean():5.0%}"
              f"   (esperado 33%)")

    res = sf[(sf.n_fuertes <= 1) & (sf.stale_prev.fillna(0) == 0)]
    print("\n" + "=" * 78)
    print(f"RESIDUO GENUINO: {len(res)} saltos IDIOSINCRÁTICOS, sin stale y sin fuente")
    print(f"({len(res)/len(d):.0%} de los {len(d)} saltos)")
    print("=" * 78)
    print(f"  {'activo':<10}{'fecha':<12}{'ret':>9}{'z':>7}")
    orden = res.z.abs().sort_values(ascending=False).index
    for r in res.reindex(orden).head(20).itertuples():
        print(f"  {r.tic:<10}{str(r.fecha.date()):<12}{r.ret:9.1%}{r.z:7.1f}")
    res.to_csv(INTERIM / "saltos_sin_fuente.csv", index=False, encoding="utf-8")
    print(f"\n  -> {INTERIM / 'saltos_sin_fuente.csv'}")


if __name__ == "__main__":
    main()
