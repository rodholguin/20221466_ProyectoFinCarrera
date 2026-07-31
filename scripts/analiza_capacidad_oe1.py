"""Capacidad y liquidez OFICIALES para el entorno de OE1.

El riesgo #1 de la tesis (iliquidez/ejecutabilidad) tenía dos piezas sin dato:
el TOPE DE CAPACIDAD del portafolio y una medida creíble de días ejecutables.
Con el Informe Bursátil Mensual ambas dejan de ser supuestos:

  - `monto_pen`   : monto efectivamente negociado en el mes (S/), oficial.
  - `frecuencia`  : % de sesiones del mes con negociación, oficial. Es la medida
                    CORRECTA de ejecutabilidad; nuestro proxy `1 - is_stale` mide
                    días con precio DISTINTO y por tanto SUBESTIMA la negociación
                    (se puede operar sin mover el precio).
  - `rotacion`    : % del flotante que rotó en el mes.

Salida: por activo, monto negociado diario medio y el tope de posición a 1/5/10%
de participación de mercado, más el contraste frecuencia oficial vs proxy.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.market import bvl_infmen
from src.universe import Config

PARTICIPACION = (0.01, 0.05, 0.10)


def calendario_sesiones(cfg) -> pd.Series:
    """N° de sesiones bursátiles por mes, desde la BVL (activo más líquido)."""
    from pathlib import Path

    from src.market.market_client import fetch_bvl

    for nem in ("FERREYC1", "ALICORC1", "CREDITC1"):
        asset = next((a for a in cfg.assets if a.bvl == nem), None)
        if asset is None:
            continue
        p = Path(cfg.paths["raw"]) / f"market_{nem}_bvl.parquet"
        df = pd.read_parquet(p) if p.exists() else fetch_bvl(asset, cfg.start, cfg.end)
        if df is None or df.empty:
            continue
        fechas = pd.to_datetime(df["date"]).dt.normalize().drop_duplicates()
        return fechas.groupby(pd.PeriodIndex(fechas, freq="M")).size()
    return pd.Series(dtype=int)


def proxy_is_stale(cfg, nem: str) -> float:
    """% de días con precio DISTINTO al día previo (el proxy que usamos hoy)."""
    from pathlib import Path

    from src.market.market_client import fetch_bvl

    asset = next((a for a in cfg.assets if a.bvl == nem), None)
    if asset is None:
        return float("nan")
    p = Path(cfg.paths["raw"]) / f"market_{nem}_bvl.parquet"
    df = pd.read_parquet(p) if p.exists() else fetch_bvl(asset, cfg.start, cfg.end)
    if df is None or df.empty:
        return float("nan")
    close = df.sort_values("date")["close"]
    return 100.0 * float((close.diff().fillna(0) != 0).mean())


def main() -> None:
    cfg = Config.load("config.yaml")
    panel = bvl_infmen.load_mensual()
    if panel.empty:
        print("No hay panel mensual. Corre antes scripts/gen_bvl_mensual.py")
        return

    sesiones = calendario_sesiones(cfg)
    print(f"Calendario: {len(sesiones)} meses, mediana "
          f"{sesiones.median():.0f} sesiones/mes\n")

    filas = []
    for asset in cfg.assets:
        sub = bvl_infmen.panel_activo(asset.bvl, panel)
        sub = sub[sub["monto_pen"].notna() & (sub["monto_pen"] > 0)]
        if sub.empty:
            print(f"  {asset.bvl}: sin meses con negociación")
            continue

        s = sub.set_index("periodo")
        ses = sesiones.reindex(s.index)
        frec = s["frecuencia"].clip(upper=100) / 100.0
        dias_op = (ses * frec).replace(0, np.nan)
        diario = s["monto_pen"] / dias_op

        filas.append({
            "activo": asset.bvl,
            "meses": len(s),
            "frec_oficial": float(s["frecuencia"].median()),
            "proxy_precio": proxy_is_stale(cfg, asset.bvl),
            "monto_mes_med": float(s["monto_pen"].median()),
            "dias_op_med": float(dias_op.median()),
            "monto_dia_med": float(diario.median()),
            "monto_dia_p25": float(diario.quantile(0.25)),
            "rotacion_med": float(s["rotacion"].median()),
        })

    res = pd.DataFrame(filas).sort_values("monto_dia_med", ascending=False)

    print("=" * 92)
    print("LIQUIDEZ OFICIAL vs NUESTRO PROXY")
    print("=" * 92)
    print(f"  {'activo':10s} {'meses':>6s} {'frec.oficial':>13s} {'proxy 1-stale':>14s} "
          f"{'brecha':>8s} {'rotación/mes':>13s}")
    for _, r in res.iterrows():
        brecha = r["frec_oficial"] - r["proxy_precio"]
        print(f"  {r['activo']:10s} {r['meses']:6.0f} {r['frec_oficial']:12.1f}% "
              f"{r['proxy_precio']:13.1f}% {brecha:+7.1f}pp {r['rotacion_med']:12.3f}%")
    print("\n  La brecha positiva = días en que SÍ se negoció pero el precio no se movió.")
    print("  Es la medida en que `1 - is_stale` subestima la ejecutabilidad real.")

    print("\n" + "=" * 92)
    print("CAPACIDAD: monto negociado y tope de posición por participación de mercado")
    print("=" * 92)
    print(f"  {'activo':10s} {'S/ negoc./mes':>15s} {'días op':>8s} "
          f"{'S/ por día':>13s} " + " ".join(f"{int(p*100):>3d}% part.".rjust(13)
                                             for p in PARTICIPACION))
    for _, r in res.iterrows():
        topes = " ".join(f"{r['monto_dia_med'] * p:>13,.0f}" for p in PARTICIPACION)
        print(f"  {r['activo']:10s} {r['monto_mes_med']:15,.0f} "
              f"{r['dias_op_med']:8.1f} {r['monto_dia_med']:13,.0f} {topes}")

    print("\n  (medianas sobre todos los meses; 'S/ por día' = monto del mes ÷ días operados)")

    print("\n" + "=" * 92)
    print("TAMAÑO DE POSICIÓN SOSTENIBLE (días para deshacerla)")
    print("=" * 92)
    print("  El monto por día acota el TRADE diario, no el tamaño del portafolio.")
    print("  Para pasar de uno al otro hay que fijar un supuesto de salida: aquí,")
    print("  'la posición debe poder liquidarse en N sesiones tomando el 10% del")
    print("  volumen diario'. Es el criterio estándar de capacidad y deja el")
    print("  supuesto a la vista en vez de esconderlo en una multiplicación.")
    print(f"\n  {'activo':10s} {'S/ por día':>13s} " +
          " ".join(f"pos. max {n}d".rjust(15) for n in (1, 5, 20)))
    for _, r in res.iterrows():
        topes = " ".join(f"{r['monto_dia_med'] * 0.10 * n:>15,.0f}" for n in (1, 5, 20))
        print(f"  {r['activo']:10s} {r['monto_dia_med']:13,.0f} {topes}")

    peor = res.loc[res["monto_dia_med"].idxmin()]
    pos20 = peor["monto_dia_med"] * 0.10 * 20
    print(f"\n  El activo más delgado en DINERO es {peor['activo']} "
          f"(S/ {peor['monto_dia_med']:,.0f}/día).")
    print(f"  Un portafolio equiponderado se dimensiona por él: con salida en 20")
    print(f"  sesiones al 10% de participación, la posición tope es "
          f"S/ {pos20:,.0f},")
    print(f"  es decir ~S/ {pos20 * len(res):,.0f} de cartera total en {len(res)} activos.")
    print("  Ponderar por liquidez en vez de equiponderar relaja bastante este techo.")

    print("\n  Percentil 25 del monto diario (meses malos, el caso que manda):")
    for _, r in res.iterrows():
        print(f"    {r['activo']:10s} S/ {r['monto_dia_p25']:>12,.0f}/día")


if __name__ == "__main__":
    main()
