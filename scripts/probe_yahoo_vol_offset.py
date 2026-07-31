"""Por que el volumen Yahoo != quantityNegotiated de la BVL en la misma fecha?

El TEST 1 de probe_yahoo_confiabilidad.py mostro que el CLOSE coincide EXACTO en
los 7 activos pero el volumen no, y sin direccion consistente (Yahoo a veces
mayor, a veces menor). Antes de concluir hay que descartar lo barato:

  H1 (desfase de fecha): el volumen de la BVL para el dia D aparece en Yahoo en
     D+1 o D-1. Se refuta si ninguna fecha vecina de Yahoo reproduce el numero.
  H2 (escala): Yahoo reporta en otra unidad (lotes, miles). Se refuta si la razon
     Yahoo/BVL no es constante entre activos.
  H3 (mecanismo de negociacion): la BVL suma ruedas/mecanismos que Yahoo no
     (o al reves). Compatible con una razon NO constante y sin signo fijo.

Imprime las ultimas filas de Yahoo junto al dato oficial para inspeccion directa.
"""
from __future__ import annotations

import pandas as pd
import requests
import yfinance as yf

_DOD = "https://dataondemand.bvl.com.pe"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": "https://www.bvl.com.pe",
    "Referer": "https://www.bvl.com.pe/",
    "Accept": "application/json, text/plain, */*",
}

ACTIVOS = {
    "MINSURI1": "62200",
    "INRETC1":  "74222",
    "CPACASC1": "23950",
    "FERREYC1": "73600",
    "LUSURC1":  "70252",
    "ALICORC1": None,
    "CREDITC1": None,
}
YTK = {k: f"{k}.LM" for k in ACTIVOS}


def bvl_ultimo(cc: str, nem: str) -> dict | None:
    try:
        r = requests.get(f"{_DOD}/v1/issuers/{cc}/value", headers=_HEADERS, timeout=25)
        r.raise_for_status()
        for e in r.json():
            if (e.get("nemonico") or "").upper() == nem.upper():
                llv = e.get("listLastValue") or []
                return llv[0] if llv else None
    except Exception as exc:
        print(f"  [BVL] {nem}: {exc}")
    return None


def main() -> None:
    print("Ultimas sesiones de Yahoo vs el dato oficial BVL del ultimo dia\n")
    razones: dict[str, float] = {}

    for nem, cc in ACTIVOS.items():
        if cc is None:
            print(f"\n=== {nem}: sin companyCode a mano, se omite el ancla ===")
            continue
        llv = bvl_ultimo(cc, nem)
        if not llv:
            print(f"\n=== {nem}: sin listLastValue ===")
            continue

        fecha = pd.to_datetime(llv["dateTimP"], dayfirst=True).normalize()
        qn = float(llv.get("quantityNegotiated") or 0)
        close_bvl = float(llv.get("close") or 0)

        raw = yf.Ticker(YTK[nem]).history(
            start=(fecha - pd.Timedelta(days=20)).strftime("%Y-%m-%d"),
            end=(fecha + pd.Timedelta(days=4)).strftime("%Y-%m-%d"),
            auto_adjust=False)

        print(f"\n=== {nem} ===  BVL {fecha.date()}: "
              f"volumen={qn:,.0f}  close={close_bvl:.4f}")
        if raw is None or raw.empty:
            print("   Yahoo sin datos")
            continue

        y = raw.reset_index()[["Date", "Close", "Volume"]]
        s = pd.to_datetime(y["Date"])
        if s.dt.tz is not None:
            s = s.dt.tz_convert(None)
        y["Date"] = s.dt.normalize()

        print(f"   {'fecha':12s} {'close':>10s} {'volumen':>14s}  {'vol/BVL':>8s}  marca")
        for _, r in y.tail(8).iterrows():
            v = float(r["Volume"])
            ratio = v / qn if qn else float("nan")
            marca = ""
            if qn and abs(v - qn) < 1e-6:
                marca = "<<< COINCIDE EXACTO con el oficial"
            elif r["Date"] == fecha:
                marca = "<-- misma fecha que el oficial"
            print(f"   {r['Date'].date()!s:12s} {r['Close']:10.4f} {v:14,.0f} "
                  f"{ratio:8.3f}  {marca}")

        fila = y[y["Date"] == fecha]
        if not fila.empty and qn:
            razones[nem] = float(fila["Volume"].iloc[0]) / qn

    print("\n" + "=" * 70)
    print("H2 (escala): razon Yahoo/BVL en la MISMA fecha")
    for nem, r in razones.items():
        print(f"   {nem:10s} {r:8.4f}")
    if razones:
        vals = list(razones.values())
        print(f"   -> min={min(vals):.3f}  max={max(vals):.3f}")
        if max(vals) / min(vals) > 1.5:
            print("   H2 REFUTADA: la razon no es constante (no es un cambio de unidad).")
        else:
            print("   H2 compatible: razon aproximadamente constante.")


if __name__ == "__main__":
    main()
