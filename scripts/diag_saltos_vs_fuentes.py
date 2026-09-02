"""¿Qué explica los SALTOS grandes de precio: los hechos de importancia o la prensa?
¿Y quién llega PRIMERO?

Contesta tres preguntas del autor (2026-08-30), todas con datos ya en el repo:

  (1) ¿Los saltos grandes están explicados por hechos de importancia? Es la
      premisa de la que depende la idea de mover R5 de prensa a hechos.
  (2) ¿Conviene REEMPLAZAR la prensa por los hechos, o sumarlos?
  (3) La prensa, ¿llega TARDE (como en el caso de Luz del Sur, 15 días) o puede
      ADELANTARSE? Rumores y filtraciones de una adquisición pueden mover el
      precio ANTES de la divulgación oficial: si eso pasa seguido, la prensa
      tiene información que el feed oficial NO tiene, y reemplazarla sería
      destruir señal.

MÉTODO
  - Retorno diario sobre close_total_return. z = ret / volatilidad TRAILING de
    60 sesiones (causal: solo mira hacia atrás).
  - SALTO = |z| >= UMBRAL_Z, con retorno no nulo. Se descartan los saltos que
    siguen a una racha de precio congelado: en un mercado ralo un precio stale
    seguido de puesta al día produce un salto FALSO (es el problema de D8 /
    is_no_trade). Ver STALE_MIN.
  - Para cada salto se mira una ventana de VENTANA días naturales hacia atrás
    (T-k .. T) y se busca: hecho de importancia, y noticia.
  - Los hechos con registerDate después de HORA_CORTE se imputan al día
    siguiente: divulgar a las 19:00 no puede mover el cierre de ese día. Misma
    convención que src/fundamentals/fundamentals_client.

LÍMITE DECLARADO: esto mide COINCIDENCIA TEMPORAL, no causalidad. Un hecho en la
ventana no prueba que el hecho causó el salto. Con ~40 hechos por emisor y año,
una ventana de 3 días tiene una tasa base de coincidencia alta: por eso se
reporta también la COBERTURA ESPERADA POR AZAR (días sin salto), que es el
contrafáctico correcto. Sin ese contraste el número de cobertura no dice nada.

Uso:
  python scripts/diag_saltos_vs_fuentes.py
  python scripts/diag_saltos_vs_fuentes.py --umbral-z 4 --ventana 5
"""
from __future__ import annotations

import argparse
import ast
import json
import re
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

HORA_CORTE = 16          # hechos divulgados a esta hora o después -> día siguiente
STALE_MIN = 3            # sesiones consecutivas con retorno 0 que invalidan el salto
VOL_VENTANA = 60

RUT_CODE = {"E05", "L01", "E01", "L40", "B03", "Z96", "L11", "E02",
            "L02", "L03", "E04", "E03"}
RUT_TXT = re.compile(
    r"(ee\.?\s?ff|estados?\s+financieros?|informaci[oó]n\s+financiera|"
    r"al\s+\d{1,2}[-/ ](ene|feb|mar|abr|may|jun|jul|ago|set|sep|oct|nov|dic)|"
    r"posici[oó]n\s+mensual|memoria\s+anual|tenedores\s+de\s+adrs?|"
    r"transacciones\s+efectuadas\s+con\s+adrs?|c[oó]digo\s+de\s+buen\s+gobierno)", re.I)


def hechos(tic: str) -> pd.DataFrame:
    f = CACHE / f"bvl_hechos_{RPJ[tic]}_2012_2025.json"
    filas = []
    for x in json.loads(f.read_text(encoding="utf-8")):
        c = x.get("codes")
        if isinstance(c, str):
            try:
                c = ast.literal_eval(c)
            except (ValueError, SyntaxError):
                c = []
        c = c or [{}]
        ts = pd.to_datetime(str(x.get("registerDate")), errors="coerce")
        if pd.isna(ts):
            continue
        obs = str(x.get("observation") or "").strip()
        cod = c[0].get("codeHHII") or ""
        # imputación por hora de divulgación
        efectiva = ts.normalize() + pd.Timedelta(days=1 if ts.hour >= HORA_CORTE else 0)
        filas.append({"ts": ts, "fecha": efectiva.normalize(), "codigo": cod,
                      "obs": obs,
                      "rutina": bool(cod in RUT_CODE or RUT_TXT.search(obs))})
    d = pd.DataFrame(filas)
    return d[(d.fecha >= "2012-01-01") & (d.fecha <= "2025-12-31")]


def noticias(tic: str) -> pd.DataFrame:
    f = RAW / f"news_{tic}.parquet"
    if not f.exists():
        return pd.DataFrame(columns=["fecha", "title"])
    d = pd.read_parquet(f)
    d["fecha"] = pd.to_datetime(d["publish_date"], errors="coerce").dt.normalize()
    return d.dropna(subset=["fecha"])[["fecha", "title"]]


def mercado(tic: str) -> pd.DataFrame:
    d = pd.read_parquet(INTERIM / f"market_{tic}.parquet")
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    s = d["close_total_return"].astype(float)
    r = s.pct_change()
    vol = r.shift(1).rolling(VOL_VENTANA, min_periods=30).std()
    out = pd.DataFrame({"ret": r, "vol": vol})
    out["z"] = out.ret / out.vol
    # racha de precio congelado inmediatamente anterior -> salto sospechoso
    cero = (out.ret.abs() < 1e-9).astype(int)
    out["stale_prev"] = cero.shift(1).rolling(STALE_MIN).sum()
    return out.dropna(subset=["z"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--umbral-z", type=float, default=3.0)
    ap.add_argument("--ventana", type=int, default=3, help="días naturales hacia atrás")
    a = ap.parse_args()
    V = pd.Timedelta(days=a.ventana)

    print("=" * 78)
    print(f"SALTOS DE PRECIO (|z| >= {a.umbral_z}) vs FUENTES DE EVENTOS")
    print(f"ventana de atribución: T-{a.ventana}d .. T   ·  corte horario {HORA_CORTE}:00")
    print("=" * 78)

    tot = {"n": 0, "hecho": 0, "noticia": 0, "ambos": 0, "ninguno": 0,
           "hecho_no_rut": 0}
    base = {"n": 0, "hecho": 0, "hecho_no_rut": 0, "noticia": 0}
    leads = []
    detalle = []

    for tic in RPJ:
        m = mercado(tic)
        h = hechos(tic)
        nz = noticias(tic)
        hs = h.fecha.values
        hs_nr = h[~h.rutina].fecha.values
        ns = nz.fecha.values

        saltos = m[(m.z.abs() >= a.umbral_z) & (m.ret.abs() > 1e-9)
                   & (m.stale_prev.fillna(0) < STALE_MIN)]
        normales = m[(m.z.abs() < 1.0) & (m.ret.abs() > 1e-9)]

        def hay(arr, t):
            return bool(((arr >= np.datetime64(t - V)) & (arr <= np.datetime64(t))).any())

        c = {"n": len(saltos), "hecho": 0, "noticia": 0, "ambos": 0,
             "ninguno": 0, "hecho_no_rut": 0}
        for t, row in saltos.iterrows():
            eh, en = hay(hs, t), hay(ns, t)
            c["hecho"] += eh
            c["noticia"] += en
            c["hecho_no_rut"] += hay(hs_nr, t)
            c["ambos"] += eh and en
            c["ninguno"] += (not eh) and (not en)
            if eh and en:
                # ¿quién llegó primero dentro de la ventana?
                fh = h[(h.fecha >= t - V) & (h.fecha <= t)].fecha.min()
                fn = nz[(nz.fecha >= t - V) & (nz.fecha <= t)].fecha.min()
                leads.append((fn - fh).days)
            if abs(row.z) >= 6:
                detalle.append((tic, t.date(), row.ret, row.z, eh, en))

        # contrafáctico: tasa base en días SIN salto
        bn = min(len(normales), 400)
        sn = normales.sample(bn, random_state=7) if bn else normales
        base["n"] += bn
        base["hecho"] += sum(hay(hs, t) for t in sn.index)
        base["hecho_no_rut"] += sum(hay(hs_nr, t) for t in sn.index)
        base["noticia"] += sum(hay(ns, t) for t in sn.index)

        for k in tot:
            tot[k] += c[k]
        if c["n"]:
            print(f"  {tic:<10} saltos={c['n']:3d}   hecho {c['hecho']/c['n']:5.0%}"
                  f"   noticia {c['noticia']/c['n']:5.0%}"
                  f"   ambos {c['ambos']/c['n']:5.0%}"
                  f"   NINGUNO {c['ninguno']/c['n']:5.0%}")

    n = tot["n"]
    print("\n" + "=" * 78)
    print("[1] COBERTURA DE LOS SALTOS  — y el contrafáctico que la hace interpretable")
    print("=" * 78)
    print(f"  saltos analizados: {n}")
    print(f"  {'':22}{'en saltos':>12}{'en días normales':>18}{'lift':>8}")
    for k, lab in (("hecho", "hay hecho"), ("hecho_no_rut", "hay hecho NO rutina"),
                   ("noticia", "hay noticia")):
        pb = base[k] / base["n"] if base["n"] else float("nan")
        ps = tot[k] / n if n else float("nan")
        print(f"  {lab:<22}{ps:12.0%}{pb:18.0%}{ps/pb if pb else float('nan'):8.2f}")
    print(f"  {'NINGUNA de las dos':<22}{tot['ninguno']/n:12.0%}")
    print(f"  {'ambas':<22}{tot['ambos']/n:12.0%}")

    if leads:
        L = pd.Series(leads)
        print("\n" + "=" * 78)
        print("[2] ¿QUIÉN LLEGA PRIMERO? (días: negativo = LA PRENSA SE ADELANTA)")
        print("=" * 78)
        print(f"  casos con ambas fuentes: {len(L)}")
        print(f"  prensa ANTES que el hecho : {(L < 0).mean():5.0%}")
        print(f"  mismo día                 : {(L == 0).mean():5.0%}")
        print(f"  prensa DESPUÉS            : {(L > 0).mean():5.0%}")
        print(f"  mediana de (prensa - hecho): {L.median():+.0f} días")

    if detalle:
        print("\n" + "=" * 78)
        print("[3] LOS SALTOS EXTREMOS (|z| >= 6) UNO POR UNO")
        print("=" * 78)
        print(f"  {'activo':<10}{'fecha':<12}{'ret':>9}{'z':>7}  {'hecho':>6}{'noticia':>8}")
        for tic, f, r, z, eh, en in sorted(detalle, key=lambda x: -abs(x[3]))[:25]:
            print(f"  {tic:<10}{str(f):<12}{r:9.1%}{z:7.1f}  "
                  f"{'SI' if eh else '--':>6}{'SI' if en else '--':>8}")


if __name__ == "__main__":
    main()
