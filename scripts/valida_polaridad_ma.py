"""¿Es correcto etiquetar TODA reestructuración/M&A como `neutral`?

EL PROBLEMA. La convención de anotación "M&A siempre neutral" hace que la
categoría A más frecuente del corpus —13 de 54 eventos relevantes, 31.2% de la
masa de magnitud— no aporte DIRECCIÓN al canal. D15 ya resolvió que esos eventos
produzcan señal (entran por `sent_neu_ewma`: intensidad y decaimiento), pero no
el signo.

LA HIPÓTESIS. "M&A" mezcla tres papeles con signos esperados distintos:
    objetivo  — se paga prima de control      -> positivo
    comprador — dilución, riesgo de integración -> ~0 / levemente negativo
    vendedor  — foco y caja                    -> ~0 / levemente positivo
Si eso se sostiene, `neutral` es correcto para el comprador y ESTÁ MAL para el
objetivo, que es justo donde vive el movimiento grande.

CÓMO SE MIDE, Y LA TRAMPA QUE HAY QUE EVITAR. Se miran los retornos alrededor
del evento. PERO:

    ESTO NO ES —Y NO PUEDE SER— UNA FORMA DE ETIQUETAR.
    Etiquetar cada evento por su retorno realizado sería LOOK-AHEAD puro y
    envenenaría el backtest entero. Lo que se valida acá es una REGLA EX-ANTE
    ("si la empresa es el objetivo, el signo es positivo"), del mismo modo que
    la magnitud de la taxonomía la fija el autor ex-ante. La regla se aplica
    después SIN mirar el precio. El `rol` es legible en el titular; el retorno
    solo sirve para decidir si la regla vale la pena.

Además la muestra es minúscula (13 eventos, 3 objetivos). Esto NO prueba nada
con significancia estadística y no se debe presentar como si lo hiciera: es una
inspección para decidir si vale la pena separar el campo `rol`.

Uso:
  python scripts/valida_polaridad_ma.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

VH = ROOT / "data" / "interim" / "validacion_humana"
INTERIM = ROOT / "data" / "interim"

# `rol` asignado por LECTURA DEL TITULAR, no del precio. Es la variable
# explicativa; asignarla mirando el retorno invalidaría la prueba.
ROL = {
    36:  ("comprador", "InRetail financia la compra de Mifarma"),
    62:  ("vendedor",  "Minsur vende su operación en Brasil"),
    75:  ("tercero",   "Sodimac compra Maestro: competidores de Saga"),
    153: ("vendedor",  "Grupo Falabella vende su parte en Juan Valdez"),
    157: ("objetivo",  "Sempra pone en venta su unidad peruana (Luz del Sur)"),
    160: ("comprador", "el grupo adquiere Joinnus"),
    174: ("interno",   "reordenamiento societario de Luz del Sur"),
    191: ("tercero",   "Sodimac compra Maestro: competidores de Saga"),
    206: ("comprador", "Alicorp adquiere Pastificio Santa Amália"),
    215: ("comprador", "Alicorp compra Fino y SAO"),
    391: ("objetivo",  "China Three Gorges compra Luz del Sur"),
    468: ("objetivo",  "Holcim adquirirá el control de Pacasmayo"),
    495: ("comprador", "InRetail compra Quicorp"),
}


def serie(ticker: str) -> pd.Series | None:
    f = INTERIM / f"market_{ticker}.parquet"
    if not f.exists():
        return None
    d = pd.read_parquet(f)
    col = ("close_total_return" if "close_total_return" in d.columns
           else "close_adj" if "close_adj" in d.columns else "close")
    d["date"] = pd.to_datetime(d["date"])
    s = d.set_index("date")[col].sort_index().astype(float)
    return s[~s.index.duplicated(keep="last")]


def ventana(s: pd.Series, fecha: pd.Timestamp, a: int, b: int) -> float:
    """Retorno acumulado entre los cierres a..b sesiones alrededor de `fecha`."""
    idx = s.index.searchsorted(fecha)
    i0, i1 = idx + a, idx + b
    if i0 < 0 or i1 >= len(s) or i0 >= i1:
        return float("nan")
    return float(s.iloc[i1] / s.iloc[i0] - 1.0)


def main() -> None:
    an = pd.ExcelFile(VH / "muestra_r5_anotar.xlsx").parse("Anotacion")
    k = pd.read_csv(VH / "clave_muestra_r5.csv")
    an = an.merge(k[["n", "ticker"]], on="n", how="left")
    ma = an[an.categoria == "A_ma_reestructuracion"].copy()
    ma["rol"] = ma.n.map(lambda x: ROL.get(x, ("?", ""))[0])
    ma["fecha"] = pd.to_datetime(ma.fecha)

    print("=" * 78)
    print("RETORNOS ALREDEDOR DE LOS 13 EVENTOS DE M&A / REESTRUCTURACIÓN")
    print("todos etiquetados hoy como `neutral` por convención")
    print("=" * 78)
    print(f"  {'n':>4} {'rol':<10} {'ticker':<9} {'fecha':<11}"
          f" {'T-1..T+1':>9} {'T..T+5':>9} {'sigma20':>8} {'en sigmas':>10}")

    filas = []
    for r in ma.sort_values(["rol", "n"]).itertuples():
        s = serie(r.ticker)
        if s is None:
            print(f"  {r.n:>4} {r.rol:<10} {r.ticker:<9} sin serie de precios")
            continue
        r3 = ventana(s, r.fecha, -1, 1)
        r5 = ventana(s, r.fecha, 0, 5)
        ret = s.pct_change()
        i = s.index.searchsorted(r.fecha)
        sig = float(ret.iloc[max(0, i - 21):max(1, i - 1)].std())
        z = r3 / sig if sig and sig == sig and sig > 0 else float("nan")
        filas.append({"n": r.n, "rol": r.rol, "r3": r3, "r5": r5, "z": z})
        print(f"  {r.n:>4} {r.rol:<10} {r.ticker:<9} {r.fecha.date()}"
              f" {r3:9.2%} {r5:9.2%} {sig:8.2%} {z:10.1f}")

    d = pd.DataFrame(filas)
    if d.empty:
        print("\nsin datos de precio utilizables.")
        return

    print("\n" + "=" * 78)
    print("RESUMEN POR ROL  (mediana; n es minúsculo, es una inspección)")
    print("=" * 78)
    print(f"  {'rol':<10} {'n':>3} {'med T-1..T+1':>13} {'med T..T+5':>12}"
          f" {'med |z|':>9} {'% con |z|>2':>12}")
    for rol, g in d.groupby("rol"):
        zz = g.z.abs()
        print(f"  {rol:<10} {len(g):>3} {g.r3.median():13.2%} {g.r5.median():12.2%}"
              f" {zz.median():9.1f} {(zz > 2).mean():12.0%}")

    obj = d[d.rol == "objetivo"]
    otros = d[d.rol.isin(["comprador", "vendedor"])]
    print("\n" + "=" * 78)
    print("LA COMPARACIÓN QUE IMPORTA")
    print("=" * 78)
    if len(obj) and len(otros):
        print(f"  OBJETIVO   (n={len(obj)}): mediana T-1..T+1 = {obj.r3.median():+.2%}"
              f"   |z| mediana = {obj.z.abs().median():.1f}")
        print(f"  COMPRADOR/ (n={len(otros)}): mediana T-1..T+1 = {otros.r3.median():+.2%}"
              f"   |z| mediana = {otros.z.abs().median():.1f}")
        print(f"  VENDEDOR")
        print(f"\n  positivos entre los OBJETIVO : {int((obj.r3 > 0).sum())}/{len(obj)}")
        print(f"  positivos entre los otros    : {int((otros.r3 > 0).sum())}/{len(otros)}")
    print("\n  RECORDATORIO: esto valida una REGLA EX-ANTE (`rol` -> signo), legible")
    print("  en el titular. NO se etiqueta ningún evento por su retorno realizado:")
    print("  eso sería look-ahead y envenenaría el backtest.")


if __name__ == "__main__":
    main()
