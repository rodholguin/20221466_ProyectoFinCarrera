"""Valida el CONTEO DE ACCIONES del pipeline contra el dato oficial de la BVL.

El P/E del panel R6 es close_raw / eps_ttm, y eps_ttm = utilidad_TTM / acciones.
Hasta ahora las acciones salían de tres vías (schedule > override > Capital
Emitido SMV ÷ nominal) SIN contraste externo. El Informe Bursátil Mensual publica
"Acciones en Circulación" por emisor y por mes, así que ahora sí hay con qué
validar — y, en el caso de InRetail, con qué REEMPLAZAR una reconstrucción.

Qué hace:
  1. Serie oficial mensual de acciones por activo, con sus PUNTOS DE QUIEBRE
     (el conteo no es constante: BCP pasó de 3.1 a 13.0 mil millones).
  2. Compara con lo que calcula hoy el pipeline, donde haya parquet de
     fundamentales en disco.
  3. Para INRETC1 emite el `shares_outstanding_schedule` EXACTO listo para
     config.yaml, que sustituye al tramo reconstruido (100,556,000, error <=2%).
"""
from __future__ import annotations

import pandas as pd

from src.market import bvl_infmen
from src.universe import Config


def puntos_de_quiebre(sub: pd.DataFrame) -> pd.DataFrame:
    """Meses en que el conteo oficial cambia respecto del mes anterior."""
    s = sub[["periodo", "acciones_circulacion"]].dropna().copy()
    if s.empty:
        return s
    s["prev"] = s["acciones_circulacion"].shift()
    quiebres = s[(s["prev"].notna()) &
                 (s["acciones_circulacion"] != s["prev"])].copy()
    quiebres["var_pct"] = 100.0 * (quiebres["acciones_circulacion"] / quiebres["prev"] - 1)
    return quiebres


def main() -> None:
    cfg = Config.load("config.yaml")
    df = bvl_infmen.load_mensual()
    if df.empty:
        print("No hay panel mensual. Corre antes scripts/gen_bvl_mensual.py")
        return

    print("=" * 88)
    print("1) SERIE OFICIAL DE ACCIONES EN CIRCULACIÓN (BVL, mensual)")
    print("=" * 88)

    for asset in cfg.assets:
        sub = bvl_infmen.panel_activo(asset.bvl, df)
        s = sub[["periodo", "acciones_circulacion"]].dropna()
        if s.empty:
            print(f"\n  {asset.bvl}: SIN datos oficiales")
            continue

        ini, fin = s.iloc[0], s.iloc[-1]
        print(f"\n  {asset.bvl}  ({len(s)} meses {s['periodo'].min()}..{s['periodo'].max()})")
        print(f"    primero {ini['periodo']}: {ini['acciones_circulacion']:>18,.0f}")
        print(f"    último  {fin['periodo']}: {fin['acciones_circulacion']:>18,.0f}")

        q = puntos_de_quiebre(sub)
        if q.empty:
            print("    conteo CONSTANTE en todo el horizonte")
        else:
            print(f"    {len(q)} cambio(s):")
            for _, r in q.iterrows():
                print(f"      {r['periodo']}  {r['prev']:>18,.0f} -> "
                      f"{r['acciones_circulacion']:>18,.0f}  ({r['var_pct']:+.2f}%)")

        # config actual, para contraste rápido
        if asset.shares_outstanding_schedule:
            print(f"    config (schedule): {asset.shares_outstanding_schedule}")
        elif getattr(asset, "shares_outstanding_override", None):
            print(f"    config (override): {asset.shares_outstanding_override:,}")
        else:
            print(f"    config: derivado de Capital Emitido SMV / nominal "
                  f"({asset.nominal_value})")

    # ── 2) contraste con lo calculado por el pipeline ────────────────────────
    print("\n" + "=" * 88)
    print("2) OFICIAL vs CALCULADO POR EL PIPELINE (donde hay fundamentales en disco)")
    print("=" * 88)

    from pathlib import Path

    from src.fundamentals.fundamentals_client import compute_shares_earnings

    raw_dir = Path(cfg.paths["raw"])
    for asset in cfg.assets:
        p = raw_dir / f"fund_{asset.bvl}_smv.parquet"
        if not p.exists():
            print(f"\n  {asset.bvl}: sin parquet de fundamentales (pendiente la corrida R4)")
            continue
        fund = pd.read_parquet(p)
        try:
            calc = compute_shares_earnings(fund, asset)
        except Exception as exc:
            print(f"\n  {asset.bvl}: no se pudo calcular ({exc})")
            continue
        if calc.empty:
            print(f"\n  {asset.bvl}: cálculo vacío")
            continue

        calc = calc.dropna(subset=["shares_outstanding"]).copy()
        calc["periodo"] = pd.PeriodIndex(pd.to_datetime(calc["period"]), freq="M")

        ofi = bvl_infmen.panel_activo(asset.bvl, df)[["periodo", "acciones_circulacion"]]
        m = calc.merge(ofi, on="periodo", how="inner").dropna(
            subset=["acciones_circulacion"])
        if m.empty:
            print(f"\n  {asset.bvl}: sin periodos comparables")
            continue

        m["dif_pct"] = 100.0 * (m["shares_outstanding"] / m["acciones_circulacion"] - 1)
        peor = m.loc[m["dif_pct"].abs().idxmax()]
        print(f"\n  {asset.bvl}: {len(m)} periodos comparados")
        print(f"    |dif| mediana {m['dif_pct'].abs().median():6.2f}%   "
              f"máxima {m['dif_pct'].abs().max():6.2f}% en {peor['periodo']}")
        print(f"    (pipeline {peor['shares_outstanding']:,.0f} vs "
              f"oficial {peor['acciones_circulacion']:,.0f})")
        dentro = 100.0 * (m["dif_pct"].abs() < 1).mean()
        print(f"    periodos con |dif| < 1%: {dentro:.0f}%")

    # ── 3) schedule oficial para InRetail ───────────────────────────────────
    print("\n" + "=" * 88)
    print("3) INRETC1 — schedule OFICIAL listo para config.yaml")
    print("=" * 88)
    sub = bvl_infmen.panel_activo("INRETC1", df)
    s = sub[["periodo", "acciones_circulacion"]].dropna()
    if s.empty:
        print("  sin datos oficiales de InRetail")
        return

    tramos: list[tuple[str, int]] = []
    prev = None
    for _, r in s.iterrows():
        v = int(r["acciones_circulacion"])
        if v != prev:
            tramos.append((str(r["periodo"].to_timestamp(how="start").date()), v))
            prev = v

    print("\n    shares_outstanding_schedule:")
    for fecha, v in tramos:
        print(f'      - ["{fecha}", {v}]')
    inret = next((a for a in cfg.assets if a.bvl == "INRETC1"), None)
    vigente = (inret.shares_outstanding_schedule or ()) if inret else ()
    print("\n  Config vigente (el primer tramo es RECONSTRUIDO, error <=2%):")
    for fecha, v in vigente:
        print(f'      - ["{fecha}", {v}]')

    if vigente and tramos:
        recon = float(vigente[0][1])
        oficial = float(tramos[0][1])
        print(f"\n  Tramo inicial: reconstruido {recon:,.0f} vs oficial "
              f"{oficial:,.0f}  ({100*(recon/oficial - 1):+.2f}%)")
        print("  => el oficial reemplaza a la reconstrucción y ELIMINA esa limitación.")


if __name__ == "__main__":
    main()
