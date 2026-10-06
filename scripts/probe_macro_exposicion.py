"""¿Qué factores macro mueven de verdad a los activos de la BVL? (evidencia propia)

Pregunta del autor (2026-08-22): el oro no le toca directamente a casi ningún
activo del universo, y el petróleo tampoco — ¿aun así impactan? Este script lo
mide sobre los datos del proyecto en vez de suponerlo.

QUÉ HACE
  1. Trae del BCRP dos series que no estaban en el panel: petróleo WTI diario
     (PD04705XD) y estaño mensual (PN01653XM).
  2. Convierte cada factor a su forma estacionaria: retorno log para precios y
     tipo de cambio, primera diferencia para EMBI y tasa de referencia.
  3. Para cada activo corre la correlación factor a factor y una regresión
     multifactor conjunta, con errores estándar de Newey-West.

DOS CUIDADOS QUE CAMBIAN EL RESULTADO
  - DÍAS SIN COTIZAR. La BVL es ilíquida: un precio que no se movió porque nadie
    transó no es un retorno de cero, es un dato ausente. Se excluyen los días
    `is_stale`; incluirlos ATENÚA cualquier correlación hacia cero y haría
    concluir "no hay efecto" por un artefacto de liquidez.
  - HORARIO. Los metales de Londres cierran ANTES que la BVL, pero el WTI y el
    EMBI se mueven durante la sesión de Lima y después. La correlación
    contemporánea mezcla ambos casos, así que se reporta también el rezago de un
    día: si el efecto real llega con retraso, aparece ahí.

Uso:
  python scripts/probe_macro_exposicion.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

INTERIM = ROOT / "data" / "interim"
PANEL = ROOT / "data" / "processed" / "dataset_unificado.parquet"
EXTRA = INTERIM / "macro_extra_probe.parquet"

_URL = ("https://estadisticas.bcrp.gob.pe/estadisticas/series/api/"
        "{c}/json/{a}/{b}")
_H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
_MES = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6, "Jul": 7,
        "Ago": 8, "Set": 9, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12}

# Precios -> retorno log. Tasas/spreads -> primera diferencia (ya son %/pbs).
EN_LOG = {"macro_cobre", "macro_oro", "macro_tc_usdpen", "macro_wti",
          "macro_estano"}
# Series de frecuencia mensual: su cambio diario es cero de verdad, no un feriado.
MENSUALES = {"macro_estano", "macro_tasa_ref", "macro_inflacion"}


def _bcrp(code: str, ini: str = "2011-01-01", fin: str = "2025-12-31") -> pd.Series:
    r = urllib.request.Request(_URL.format(c=code, a=ini, b=fin), headers=_H)
    d = json.load(urllib.request.urlopen(r, timeout=40))
    idx, val = [], []
    for p in d["periods"]:
        v = p["values"][0]
        if v == "n.d.":
            continue
        n = p["name"]
        if n.count(".") == 2:                       # '02.Ene.20' -> diaria
            dia, mes, aa = n.split(".")
            ts = pd.Timestamp(2000 + int(aa), _MES[mes], int(dia))
        else:                                       # 'Ene.2012'  -> mensual
            mes, aaaa = n.split(".")
            ts = pd.Timestamp(int(aaaa), _MES[mes], 1)
        idx.append(ts)
        val.append(float(v))
    return pd.Series(val, index=pd.DatetimeIndex(idx)).sort_index()


def cargar_macro() -> pd.DataFrame:
    m = pd.read_parquet(INTERIM / "macro_bcrp.parquet")

    if EXTRA.exists():
        ex = pd.read_parquet(EXTRA)
    else:
        print("Descargando del BCRP: WTI diario y estaño mensual ...")
        wti = _bcrp("PD04705XD").rename("macro_wti")
        est = _bcrp("PN01653XM").rename("macro_estano")
        # El estaño es PROMEDIO DEL MES: solo se conoce cuando el mes cerró, así
        # que se hace efectivo el primer día del mes siguiente (misma disciplina
        # point-in-time que la inflación). Sin esto habría look-ahead.
        est.index = est.index + pd.offsets.MonthBegin(1)
        ex = pd.concat([wti, est], axis=1).sort_index()
        ex.to_parquet(EXTRA)
        print(f"  WTI {wti.notna().sum()} obs · estaño {est.notna().sum()} obs\n")

    m = m.join(ex, how="outer").sort_index()
    m["macro_estano"] = m["macro_estano"].ffill()
    m["macro_tasa_ref"] = m["macro_tasa_ref"].ffill()
    return m


def cambios(m: pd.DataFrame) -> pd.DataFrame:
    """Cada factor a su forma estacionaria, tratando distinto diarias y mensuales.

    La distinción NO es cosmética. En una serie DIARIA, un cambio de cero suele
    ser un feriado arrastrado por ffill: es un dato ausente disfrazado, y contarlo
    infla la muestra y atenúa las correlaciones hacia cero. En una serie MENSUAL
    (estaño, tasa, inflación) el cero es información legítima: el valor no se
    movió ese día porque solo cambia una vez al mes. Anular ambos por igual —el
    error de la primera versión— dejaba la regresión conjunta con n=17.
    """
    out = {}
    for c in m.columns:
        if c in MENSUALES:
            s = m[c].ffill()
            out[c] = (np.log(s).diff() if c in EN_LOG else s.diff())
        else:
            s = m[c]                      # sin ffill: el feriado queda NaN
            d = np.log(s).diff() if c in EN_LOG else s.diff()
            out[c] = d.replace(0.0, np.nan)
    return pd.DataFrame(out)


def newey_west(X: np.ndarray, y: np.ndarray, rezagos: int = 5):
    """OLS con errores estándar HAC. Devuelve (betas, t, R2, n)."""
    n, k = X.shape
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ y
    e = y - X @ b
    S = (X * e[:, None]).T @ (X * e[:, None])
    for L in range(1, rezagos + 1):
        w = 1 - L / (rezagos + 1)
        A = (X[L:] * e[L:, None]).T @ (X[:-L] * e[:-L, None])
        S += w * (A + A.T)
    V = XtX_inv @ S @ XtX_inv
    se = np.sqrt(np.maximum(np.diag(V), 1e-18))
    r2 = 1 - (e @ e) / (((y - y.mean()) ** 2).sum())
    return b, b / se, r2, n


def estrellas(t: float, n: int) -> str:
    from scipy import stats
    p = 2 * (1 - stats.t.cdf(abs(t), max(n - 1, 1)))
    return "***" if p < 0.01 else "** " if p < 0.05 else "*  " if p < 0.10 else "   "


NOMBRE_CORTO = {"macro_cobre": "cobre", "macro_oro": "oro",
                "macro_estano": "estaño", "macro_wti": "petróleo (WTI)",
                "macro_tc_usdpen": "TC USD/PEN", "macro_embi": "EMBI Perú",
                "macro_tasa_ref": "tasa BCRP", "macro_inflacion": "inflación"}

PERFIL = {"CREDITC1": "banco", "MINSURI1": "minera estaño/cobre",
          "ALICORC1": "alimentos", "INRETC1": "retail/farma",
          "CPACASC1": "cemento", "FERREYC1": "bienes de capital",
          "LUSURC1": "electricidad",
          # universo viejo, se conservan si sus parquets siguen en disco
          "BUENAVC1": "minera oro/plata", "CORAREC1": "acero", "SAGAC1": "retail"}


def cargar_precios() -> pd.DataFrame:
    """Precios de data/interim/market_*.parquet (salida de R3).

    NO se usa el panel unificado a propósito: ese solo se regenera al correr R6,
    así que después de un R3 nuevo estaría desactualizado y silenciosamente
    dejaría fuera a los activos recién incorporados.

    `is_stale` se replica con la MISMA regla de build_dataset.py:242 (precio de
    cierre crudo idéntico al del día hábil anterior). Diferencia menor: allí se
    calcula sobre el calendario bursátil común y aquí sobre las fechas propias
    del activo, lo que si acaso SUBESTIMA los días rancios -> la prueba de
    robustez queda del lado conservador.
    """
    partes = []
    for f in sorted(INTERIM.glob("market_*.parquet")):
        d = pd.read_parquet(f)
        d["date"] = pd.to_datetime(d["date"])
        d = d.sort_values("date")
        d["is_stale"] = d["close_raw"] == d["close_raw"].shift(1)
        partes.append(d[["ticker", "date", "ret_1d", "is_stale"]])
    if not partes:
        sys.exit("No hay data/interim/market_*.parquet. Corre antes: python -m src.market")
    return pd.concat(partes, ignore_index=True)


def main() -> None:
    from scipy import stats

    panel = cargar_precios()
    panel["is_stale"] = panel["is_stale"].fillna(False).astype(bool)
    print("Activos:", ", ".join(sorted(panel.ticker.unique())), "\n")

    m = cargar_macro()
    dm = cambios(m)

    factores = ["macro_cobre", "macro_oro", "macro_estano", "macro_wti",
                "macro_tc_usdpen", "macro_embi"]

    print("=" * 78)
    print("CORRELACION DE RETORNOS DIARIOS CON CAMBIOS EN FACTORES MACRO")
    print("Solo dias efectivamente transados (is_stale excluido). 2012-2025.")
    print("=" * 78)

    tickers = sorted(panel["ticker"].unique())
    print(f"\n{'factor':16s}" + "".join(f"{t[:8]:>11s}" for t in tickers))
    print(f"{'':16s}" + "".join(f"{PERFIL.get(t, '')[:9]:>11s}" for t in tickers))
    print("-" * 78)

    filas = {}
    for f in factores:
        celdas = []
        for t in tickers:
            g = panel[(panel.ticker == t) & (~panel.is_stale)]
            s = g.set_index("date")["ret_1d"].dropna()
            j = pd.concat([s.rename("r"), dm[f].rename("x")], axis=1).dropna()
            if len(j) < 100:
                celdas.append("     -     ")
                continue
            c, p = stats.pearsonr(j["r"], j["x"])
            marca = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < .10 else ""
            celdas.append(f"{c:+.3f}{marca:<3s}".rjust(11))
            filas[(f, t)] = (c, p, len(j))
        print(f"{NOMBRE_CORTO[f]:16s}" + "".join(celdas))
    print("-" * 78)
    print("*** p<0.01  ** p<0.05  * p<0.10")

    for rezago in (0, 1):
        print("\n" + "=" * 78)
        etiqueta = ("CONTEMPORANEA" if rezago == 0 else
                    "CON FACTORES REZAGADOS UN DIA (la que importa para operar en t+1)")
        print(f"REGRESION MULTIFACTOR POR ACTIVO — {etiqueta}")
        print("t de Newey-West (5 rezagos). Todos los factores COMPITEN entre si:")
        print("un factor que solo era proxy de otro pierde su coeficiente aqui.")
        print("=" * 78)
        Xf = dm[factores].shift(rezago)
        for t in tickers:
            g = panel[(panel.ticker == t) & (~panel.is_stale)]
            s = g.set_index("date")["ret_1d"].dropna()
            j = pd.concat([s.rename("r"), Xf], axis=1).dropna()
            if len(j) < 200:
                print(f"\n{t}: muestra insuficiente ({len(j)})")
                continue
            y = j["r"].to_numpy()
            X = np.column_stack([np.ones(len(j)), j[factores].to_numpy()])
            b, tt, r2, n = newey_west(X, y)
            print(f"\n{t} ({PERFIL.get(t, '')})  n={n}  R2={r2:.3f}")
            for i, f in enumerate(factores, start=1):
                print(f"    {NOMBRE_CORTO[f]:16s} beta={b[i]:+8.4f}  "
                      f"t={tt[i]:+6.2f} {estrellas(tt[i], n)}")

    print("\n" + "=" * 78)
    print("REZAGO DE UN DIA — ¿el mercado reacciona TARDE?")
    print("=" * 78)
    print("""
Dos columnas por activo. La segunda es la prueba que decide:

  [t]     excluye los dias en que el activo no transo (is_stale en t).
  [t,t-1] exige ADEMAS que el dia ANTERIOR haya transado.

Por que importa: si el cierre de t-1 es viejo, el 'retorno de un dia' en t
abarca en realidad dos dias de informacion, y entonces va a correlacionar con
el macro de t-1 POR CONSTRUCCION. Eso seria un artefacto de precio rancio, no
una oportunidad. Si la correlacion SOBREVIVE en [t,t-1], es ajuste lento de
verdad — y eso si es explotable a t+1 (D13).""")

    def corr_filtrada(t: str, f: str, estricto: bool):
        g = panel[panel.ticker == t].sort_values("date").copy()
        st = g["is_stale"]
        ok = ~st if not estricto else (~st & ~st.shift(1).fillna(True).astype(bool))
        s = g.loc[ok].set_index("date")["ret_1d"].dropna()
        j = pd.concat([s.rename("r"), dm[f].shift(1).rename("x")], axis=1).dropna()
        if len(j) < 100:
            return None
        c, p = stats.pearsonr(j["r"], j["x"])
        return c, p, len(j)

    for t in tickers:
        print(f"\n{t} ({PERFIL.get(t, '')})")
        print(f"  {'factor':16s} {'[t]':>16s} {'[t,t-1]':>16s}   sobrevive")
        for f in factores:
            a = corr_filtrada(t, f, False)
            b = corr_filtrada(t, f, True)
            def fmt(x):
                if x is None:
                    return "        -       "
                c, p, n = x
                m = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < .10 else ""
                return f"{c:+.3f}{m:<3s} n={n:<4d}".rjust(16)
            veredicto = ""
            if a and b:
                sig_a, sig_b = a[1] < 0.05, b[1] < 0.05
                veredicto = ("si" if sig_a and sig_b else
                             "NO (era rancio)" if sig_a and not sig_b else "")
            print(f"  {NOMBRE_CORTO[f]:16s} {fmt(a)} {fmt(b)}   {veredicto}")


if __name__ == "__main__":
    main()
