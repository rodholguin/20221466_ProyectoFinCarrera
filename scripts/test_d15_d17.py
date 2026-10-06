"""Prueba de la implementación de D15 (9 columnas categóricas) y D17 (bandera).

Cubre las cuatro cosas que pueden salir mal EN SILENCIO:

  (1) El BUG DEL ROLL-FORWARD. Un evento divulgado en sábado se reasigna al lunes
      siguiente. Si ese lunes ya tenía eventos propios, los conteos deben SUMARSE.
      La versión anterior promediaba TODO por n_articles, o sea habría dividido
      los eventos entre el número de días fusionados — un sesgo sistemático
      contra lo divulgado fuera de sesión, que es justo cuando el emisor publica.
  (2) `neutral` ENTRA. Es el cambio central de D15: antes la polaridad neutra no
      aparecía en ninguna columna y se perdía el 23.3% de la masa relevante.
  (3) EL DECAIMIENTO CORRE SOBRE EL CALENDARIO COMPLETO, no sobre los días con
      noticia. Si corriera sobre las filas con prensa, el decaimiento dependería
      de cuándo hubo cobertura — exactamente lo que no se quiere.
  (4) LOS BRAZOS DE ABLACIÓN existen y son distintos entre sí.

Uso:
  python scripts/test_d15_d17.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from src.integration.build_dataset import (
    _align_sentiment_to_calendar, _sentiment_ewmas, feature_views)
from src.sentiment.emisores import nombra_empresa
from src.sentiment.llm_sentiment import aggregate_daily
from src.universe import (SENTIMENT_COUNT_COLS, SENTIMENT_HALFLIVES,
                          SENTIMENT_SCHEMA)

fallos: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(f"  {'OK  ' if cond else 'FALLA'}  {msg}")
    if not cond:
        fallos.append(msg)


def art(id_, ticker, fecha, titulo, cat, pol, mag, nom):
    return dict(id=id_, ticker=ticker, publish_date=fecha, title=titulo,
                categoria=cat, polaridad=pol, magnitud=mag,
                relevante=int(mag > 0), titular_nombra_empresa=nom, origen="llm")


print("=" * 74)
print("(A) aggregate_daily — conteos por celda, con `neutral` y con `_nom`")
print("=" * 74)
articulos = pd.DataFrame([
    # 2024-03-01 (viernes): 1 alto/negativo nombrada, 1 alto/neutral anónima
    art("1", "CREDITC1", "2024-03-01", "BCP: utilidad cae 20%",
        "resultados", "negativo", 1.0, 1),
    art("2", "CREDITC1", "2024-03-01", "Bancos peruanos y la coyuntura",
        "ma_reestructuracion", "neutral", 1.0, 0),
    # irrelevante: no debe entrar a ningún conteo de celda
    art("3", "CREDITC1", "2024-03-01", "Precio del dolar hoy",
        "mencion_incidental", None, 0.0, 0),
    # 2024-03-02 (SÁBADO): 2 eventos que deben rodar al lunes 04
    art("4", "CREDITC1", "2024-03-02", "BCP compra Helm Bank",
        "ma_reestructuracion", "positivo", 1.0, 1),
    art("5", "CREDITC1", "2024-03-02", "BCP abre agencia en Piura",
        "estrategia_inversion", "positivo", 0.6, 1),
    # 2024-03-04 (lunes): 1 evento propio -> debe SUMARSE con los del sábado
    art("6", "CREDITC1", "2024-03-04", "BCP: nuevo gerente general",
        "gobierno_corporativo", "neutral", 0.6, 1),
    # POSITIVO ANÓNIMO: hace falta para que el brazo restringido de D17 se
    # DIFERENCIE del completo en el canal `pos`. Sin él los dos brazos salen
    # idénticos en esa polaridad y el test no probaría nada.
    art("7", "CREDITC1", "2024-03-05", "La banca peruana crece 8% en el trimestre",
        "resultados", "positivo", 1.0, 0),
])
daily = aggregate_daily(articulos)
print(daily[["date", "n_articles", "n_relevantes", "n_alto_pos", "n_alto_neu",
             "n_alto_neg", "n_resto_pos", "n_resto_neu"]].to_string(index=False))

falta = [c for c in SENTIMENT_SCHEMA if c not in daily.columns]
check(not falta, f"el esquema completo se emite (faltan: {falta or 'ninguna'})")
d0 = daily[daily.date.astype(str) == "2024-03-01"].iloc[0]
check(d0.n_alto_neg == 1 and d0.n_alto_neu == 1, "1 alto/neg y 1 alto/neutral el 01-mar")
check(d0.n_alto_neu_nom == 0 and d0.n_alto_neg_nom == 1,
      "`_nom` separa: el neutral era anónimo, el negativo nombrado")
check(int(daily[[c for c in daily.columns if c.startswith("n_alto")
                 or c.startswith("n_resto")]].sum().sum()) > 0,
      "hay conteos distintos de cero")
check(d0.n_articles == 3 and d0.n_relevantes == 2,
      "el irrelevante cuenta como artículo pero no como evento")

print()
print("=" * 74)
print("(B) EL BUG DEL ROLL-FORWARD — sábado + lunes deben SUMAR, no promediar")
print("=" * 74)
calendario = pd.DatetimeIndex(pd.bdate_range("2024-02-26", "2024-03-15"))
al = _align_sentiment_to_calendar(daily, calendario)
lunes = al[al.date == pd.Timestamp("2024-03-04")].iloc[0]
print(al[["date", "n_articles", "n_relevantes", "n_alto_pos", "n_resto_pos",
          "n_resto_neu"]].to_string(index=False))
check(lunes.n_alto_pos == 1, "el M&A del sábado llegó entero al lunes (no 0.5)")
check(lunes.n_resto_pos == 1, "la inversión del sábado llegó entera al lunes")
check(lunes.n_resto_neu == 1, "el evento propio del lunes se conserva")
check(lunes.n_relevantes == 3, "3 eventos relevantes el lunes (2 del sábado + 1 propio)")
check(lunes.n_articles == 3, "3 artículos, sumados y no promediados")

print()
print("=" * 74)
print("(C) EWMAs — `neutral` entra y el decaimiento corre sobre el calendario")
print("=" * 74)
panel = pd.DataFrame({"date": calendario}).merge(al, on="date", how="left")
panel = _sentiment_ewmas(panel)
cols9 = [f"sent_{p}_ewma_{h}" for p in ("pos", "neu", "neg")
         for h in SENTIMENT_HALFLIVES]
check(all(c in panel.columns for c in cols9), "las 9 columnas del canal base existen")
check(panel["sent_neu_ewma_5"].max() > 0,
      "`sent_neu_ewma_5` es distinta de cero -> el neutral ENTRA (D15)")
print(panel[["date", "sent_pos_ewma_5", "sent_pos_ewma_60",
             "sent_neu_ewma_5", "sent_neg_ewma_5"]].to_string(index=False))
i = panel.index[panel.date == pd.Timestamp("2024-03-04")][0]
decae = panel["sent_pos_ewma_5"].iloc[i + 1:i + 6]
check(bool((decae.diff().dropna() < 0).all()) and bool((decae > 0).all()),
      "sin eventos nuevos la EWMA decae de forma monótona y no salta a cero")
# La vida media larga RETIENE MÁS EN PROPORCIÓN, no en nivel. Con `adjust=False`
# la de 5 días reacciona con un alfa mucho mayor, así que su PICO es más alto y
# su caída más rápida; la de 60 apenas se mueve pero casi no decae. Comparar
# niveles absolutos sería el error: hay que comparar cuánto conserva cada una
# respecto de su propio pico.
retencion = {h: panel[f"sent_pos_ewma_{h}"].iloc[-1] / panel[f"sent_pos_ewma_{h}"].max()
             for h in SENTIMENT_HALFLIVES}
check(retencion[60] > retencion[20] > retencion[5],
      f"a mayor vida media, mayor retención relativa: "
      f"{ {h: round(v, 3) for h, v in retencion.items()} }")
check(not panel[cols9].isna().any().any(), "ninguna de las 9 columnas tiene NaN")

print()
print("=" * 74)
print("(D) BRAZOS DE ABLACIÓN")
print("=" * 74)
panel["ticker"] = "CREDITC1"
vistas = feature_views(panel)
base = [c for c in vistas["mercado_sentimiento"] if c.startswith("sent_")]
tramos = [c for c in vistas["mercado_sentimiento_tramos"] if c.startswith("sent_")]
restr = [c for c in vistas["mercado_sentimiento_restringido"] if c.startswith("sent_")]
print(f"  base        {len(base):>2} columnas   {base[:3]} ...")
print(f"  tramos      {len(tramos):>2} columnas   {tramos[:3]} ...")
print(f"  restringido {len(restr):>2} columnas   {restr[:3]} ...")
check(len(base) == 9, "el brazo base tiene 9 columnas (D15)")
check(len(tramos) == 18, "el brazo por tramos tiene 18 columnas (ablación D15)")
check(len(restr) == 9, "el brazo restringido tiene 9 columnas (ablación D17)")
check(set(base).isdisjoint(restr), "base y restringido son columnas distintas")
for pol in ("pos", "neu"):
    check(not panel[f"sent_{pol}_ewma_5"].equals(panel[f"sent_{pol}_nom_ewma_5"]),
          f"canal `{pol}`: el brazo restringido difiere del completo")
check(bool((panel["sent_pos_nom_ewma_5"] <= panel["sent_pos_ewma_5"] + 1e-12).all()),
      "el restringido nunca supera al completo (es un subconjunto)")

print()
print("=" * 74)
print("(E) La bandera de D17 sobre titulares reales")
print("=" * 74)
for tk, t, esperado in [
        ("CREDITC1", "BCP compra Helm Bank", True),
        ("CREDITC1", "Precio del dolar hoy, martes 30 de diciembre", False),
        ("CREDITC1", "Yape permite recibir el sueldo en billetera digital", True),
        ("FERREYC1", "Ministro Ferreyros anuncia vuelos de Latam", False),
        ("FERREYC1", "Ferreyros supera su record de ventas", True),
        ("CPACASC1", "Holcim adquiere participacion mayoritaria de Pacasmayo", True)]:
    got = nombra_empresa(tk, t)
    check(got == esperado, f"[{tk}] {t[:52]!r} -> {got}")

print()
print("=" * 74)
print(f"RESULTADO: {'TODO OK' if not fallos else f'{len(fallos)} FALLAS'}")
print("=" * 74)
if fallos:
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
