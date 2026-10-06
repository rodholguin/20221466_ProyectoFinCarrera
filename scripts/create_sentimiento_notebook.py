"""Genera notebooks/resultados_sentimiento_R5.ipynb (R5 rediseñado, universo de 7).

Reemplaza como evidencia de R5 a notebooks/exploracion_sentimiento_bvl.ipynb, que
documenta el canal v1 (score continuo de gemma3:4b sobre el universo de 5) y se
conserva solo como registro histórico.
"""
import json
from pathlib import Path


def code_cell(source: str, cell_id: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "id": cell_id,
            "metadata": {}, "outputs": [], "source": source}


def md_cell(source: str, cell_id: str) -> dict:
    return {"cell_type": "markdown", "id": cell_id, "metadata": {}, "source": source}


cells = []

cells.append(md_cell(
    "# R5 — Resultados del canal de sentimiento rediseñado (7 empresas BVL)\n\n"
    "Corrida definitiva del 2026-09-01: **gemma3:12b** (Ollama, servidor con GPU), "
    "prompt **v2.1**, temperatura 0 y salida JSON forzada. El modelo NO asigna un "
    "puntaje de sentimiento: clasifica el **tipo de evento** en una taxonomía "
    "ex-ante de 15 categorías y solo da polaridad cuando la categoría es relevante "
    "(magnitud > 0). Las categorías de magnitud cero son el filtro de relevancia. "
    "Un prefiltro de expresiones regulares descarta antes del LLM las crónicas del "
    "índice y los patrocinios.\n\n"
    "Especificación: `docs/taxonomia_eventos_R5.txt`. Validación contra 550 titulares "
    "anotados por el autor: `docs/auditoria_anotacion_humana_R5.txt`. Decisiones "
    "D11-D19: `docs/decisiones_pendientes_OE1.txt`.\n\n"
    "Insumos: `data/interim/sentiment_articulos_<TICKER>.parquet` (un registro por "
    "titular) y el panel unificado `data/processed/dataset_unificado.parquet`.",
    "s-00"))

cells.append(code_cell(
    "import sys, pathlib\n"
    "sys.path.insert(0, str(pathlib.Path.cwd().parent))\n\n"
    "import numpy as np\n"
    "import pandas as pd\n"
    "import matplotlib.pyplot as plt\n"
    "import seaborn as sns\n"
    "from scipy import stats\n"
    "import warnings\n"
    "warnings.filterwarnings('ignore')\n\n"
    "from src.sentiment.taxonomia import TAXONOMIA, ERROR\n\n"
    "DATA_INTERIM = pathlib.Path('../data/interim')\n"
    "DATA_PROCESSED = pathlib.Path('../data/processed')\n\n"
    "TICKERS = ['CREDITC1', 'ALICORC1', 'INRETC1', 'CPACASC1', 'FERREYC1', 'LUSURC1', 'MINSURI1']\n"
    "NOMBRES = {'CREDITC1': 'BCP', 'ALICORC1': 'Alicorp', 'INRETC1': 'InRetail',\n"
    "           'CPACASC1': 'Pacasmayo', 'FERREYC1': 'Ferreycorp', 'LUSURC1': 'Luz del Sur',\n"
    "           'MINSURI1': 'Minsur'}\n"
    "COLORES = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2']\n"
    "COLOR_MAP = dict(zip(TICKERS, COLORES))\n"
    "COLOR_POL = {'positivo': '#2a9d5c', 'neutral': '#9aa5b1', 'negativo': '#d1495b'}\n\n"
    "sns.set_theme(style='whitegrid')\n"
    "plt.rcParams.update({'figure.dpi': 110, 'axes.titlesize': 11})\n\n"
    "art = pd.concat([pd.read_parquet(DATA_INTERIM / f'sentiment_articulos_{t}.parquet')\n"
    "                 for t in TICKERS], ignore_index=True)\n"
    "art['fecha'] = pd.to_datetime(art['publish_date'])\n"
    "# `relevante` y la bandera de titular vienen como enteros 0/1: como máscara hay que\n"
    "# castearlos (indexar con un entero selecciona columnas; `~` sobre un entero es bitwise).\n"
    "art['relevante'] = art['relevante'].astype(bool)\n"
    "art['titular_nombra_empresa'] = art['titular_nombra_empresa'].astype(bool)\n"
    "panel = pd.read_parquet(DATA_PROCESSED / 'dataset_unificado.parquet')\n"
    "print(f'Titulares en el corpus: {len(art):,}')\n"
    "print(f'Con error de parseo del LLM: {(art.categoria == ERROR).sum()}')\n"
    "print(f'Clasificados: {(art.categoria != ERROR).sum():,}  |  eventos relevantes: {int(art.relevante.sum()):,}')",
    "s-01"))

cells.append(md_cell("## 1. Resumen por activo", "s-02"))

cells.append(code_cell(
    "ok = art[art.categoria != ERROR]\n"
    "res = (ok.groupby('ticker')\n"
    "         .agg(titulares=('id', 'size'),\n"
    "              por_prefiltro=('origen', lambda s: (s == 'prefiltro').sum()),\n"
    "              por_llm=('origen', lambda s: (s == 'llm').sum()),\n"
    "              nombra_empresa=('titular_nombra_empresa', 'sum'),\n"
    "              relevantes=('relevante', 'sum'))\n"
    "         .reindex(TICKERS))\n"
    "res['% relevantes'] = (res['relevantes'] / res['titulares'] * 100).round(1)\n"
    "res['% nombra empresa'] = (res['nombra_empresa'] / res['titulares'] * 100).round(1)\n"
    "anios = (panel.date.max() - panel.date.min()).days / 365.25\n"
    "res['eventos/año'] = (res['relevantes'] / anios).round(1)\n"
    "res.loc['TOTAL'] = res.sum(numeric_only=True)\n"
    "res.loc['TOTAL', ['% relevantes', '% nombra empresa', 'eventos/año']] = [\n"
    "    round(res.loc['TOTAL', 'relevantes'] / res.loc['TOTAL', 'titulares'] * 100, 1),\n"
    "    round(res.loc['TOTAL', 'nombra_empresa'] / res.loc['TOTAL', 'titulares'] * 100, 1),\n"
    "    round(res.loc['TOTAL', 'relevantes'] / anios, 1)]\n"
    "res.astype({c: int for c in ['titulares', 'por_prefiltro', 'por_llm', 'nombra_empresa', 'relevantes']})",
    "s-03"))

cells.append(md_cell(
    "## 2. Distribución de categorías de la taxonomía por activo (Figura 11)\n\n"
    "Cada barra suma el 100% de los titulares clasificados del activo. Los tonos "
    "cálidos son categorías **relevantes** (magnitud > 0: alta, media o baja); los "
    "grises son las categorías de **magnitud cero**, que funcionan como filtro de "
    "relevancia (incluye lo descartado por el prefiltro, que se etiqueta como "
    "`indice_bursatil` o `patrocinio_rse`). El \"% relev.\" es el del MODELO, que "
    "sobre-declara relevancia (precisión medida 59.3% contra la anotación del autor; la "
    "relevancia poblacional estimada es 7.2% ±2.8 pp). La gran mayoría del corpus es ruido: "
    "crónicas del índice, menciones de pasada y noticias sectoriales.",
    "s-04"))

cells.append(code_cell(
    "TRAMO = {c: ('alto' if m == 1.0 else 'medio' if m == 0.6 else 'bajo' if m == 0.3 else 'cero')\n"
    "         for c, (m, _) in TAXONOMIA.items()}\n"
    "ORDEN = sorted(TAXONOMIA, key=lambda c: (-TAXONOMIA[c][0], c))\n"
    "PALETA = {'alto': plt.cm.Reds(np.linspace(0.85, 0.55, 4)),\n"
    "          'medio': plt.cm.Oranges(np.linspace(0.75, 0.45, 4)),\n"
    "          'bajo': [plt.cm.YlOrBr(0.35)],\n"
    "          'cero': plt.cm.Greys(np.linspace(0.75, 0.25, 6))}\n"
    "colores_cat, usados = {}, {k: 0 for k in PALETA}\n"
    "for c in ORDEN:\n"
    "    tr = TRAMO[c]\n"
    "    colores_cat[c] = PALETA[tr][usados[tr]]\n"
    "    usados[tr] += 1\n\n"
    "dist = pd.crosstab(ok['ticker'], ok['categoria'], normalize='index').reindex(TICKERS)[ORDEN] * 100\n"
    "n_por = ok['ticker'].value_counts()\n\n"
    "fig, ax = plt.subplots(figsize=(14, 6.2))\n"
    "izq = np.zeros(len(TICKERS))\n"
    "for c in ORDEN:\n"
    "    v = dist[c].values\n"
    "    etiqueta = f'{c} ({TAXONOMIA[c][0]:.1f})'\n"
    "    ax.barh(range(len(TICKERS)), v, left=izq, color=colores_cat[c], label=etiqueta,\n"
    "            edgecolor='white', linewidth=0.4)\n"
    "    for i, (x0, w) in enumerate(zip(izq, v)):\n"
    "        if w >= 4:\n"
    "            ax.text(x0 + w / 2, i, f'{w:.0f}', ha='center', va='center', fontsize=7,\n"
    "                    color='white' if TRAMO[c] in ('alto', 'medio') or w > 15 else 'black')\n"
    "    izq += v\n"
    "rel = ok.groupby('ticker')['relevante'].mean().reindex(TICKERS) * 100\n"
    "ax.set_yticks(range(len(TICKERS)))\n"
    "ax.set_yticklabels([f'{NOMBRES[t]}\\nn={n_por[t]:,} · relev. {rel[t]:.1f}%' for t in TICKERS], fontsize=9)\n"
    "ax.invert_yaxis()\n"
    "ax.set_xlim(0, 100)\n"
    "ax.set_xlabel('% de los titulares clasificados del activo')\n"
    "ax.set_title(f'Categorías de la taxonomía por activo — {len(ok):,} titulares clasificados '\n"
    "             f'(magnitud ex-ante entre paréntesis)', fontweight='bold')\n"
    "ax.legend(ncol=1, fontsize=8, bbox_to_anchor=(1.01, 1), loc='upper left', title='categoría (magnitud)')\n"
    "plt.tight_layout()\n"
    "plt.show()\n\n"
    "tabla = pd.crosstab(ok['categoria'], ok['ticker']).reindex(index=ORDEN, columns=TICKERS).fillna(0).astype(int)\n"
    "tabla['TOTAL'] = tabla.sum(axis=1)\n"
    "tabla.insert(0, 'magnitud', [TAXONOMIA[c][0] for c in tabla.index])\n"
    "tabla",
    "s-05"))

cells.append(md_cell(
    "## 3. Eventos relevantes por año, activo y polaridad (Figura 12)\n\n"
    "Eventos = titulares de categoría relevante (magnitud > 0), fechados por su "
    "publicación. La polaridad la emite el modelo solo para estas categorías "
    "(positivo / neutral / negativo). La escala vertical es común a los siete "
    "activos para que se vea la heterogeneidad de cobertura (BCP frente a "
    "Pacasmayo o Ferreycorp).",
    "s-06"))

cells.append(code_cell(
    "ev = art[art['relevante']].copy()\n"
    "ev['anio'] = ev['fecha'].dt.year\n"
    "ev['polaridad'] = ev['polaridad'].fillna('neutral')\n"
    "anios_rng = range(int(ev['anio'].min()), int(ev['anio'].max()) + 1)\n"
    "POLS = ['positivo', 'neutral', 'negativo']\n\n"
    "cnt = ev.groupby(['ticker', 'anio', 'polaridad']).size().unstack('polaridad').reindex(columns=POLS).fillna(0)\n"
    "ymax = cnt.sum(axis=1).max() * 1.08\n\n"
    "fig, axes = plt.subplots(4, 2, figsize=(15, 13), sharex=True)\n"
    "axes = axes.flatten()\n"
    "for ax, t in zip(axes, TICKERS):\n"
    "    c = cnt.loc[t].reindex(anios_rng).fillna(0) if t in cnt.index.get_level_values(0) else None\n"
    "    base = np.zeros(len(c))\n"
    "    for p in POLS:\n"
    "        ax.bar(c.index, c[p], bottom=base, color=COLOR_POL[p], label=p, width=0.8)\n"
    "        base += c[p].values\n"
    "    tot = ev[ev.ticker == t]\n"
    "    ax.set_title(f'{NOMBRES[t]} — {len(tot)} eventos  (+{(tot.polaridad == \"positivo\").sum()} / '\n"
    "                 f'={(tot.polaridad == \"neutral\").sum()} / −{(tot.polaridad == \"negativo\").sum()})',\n"
    "                 fontweight='bold', color=COLOR_MAP[t])\n"
    "    ax.set_ylim(0, ymax)\n"
    "    ax.set_ylabel('eventos')\n\n"
    "# último panel: total del universo\n"
    "ax = axes[-1]\n"
    "tot = ev.groupby(['anio', 'polaridad']).size().unstack().reindex(index=anios_rng, columns=POLS).fillna(0)\n"
    "base = np.zeros(len(tot))\n"
    "for p in POLS:\n"
    "    ax.bar(tot.index, tot[p], bottom=base, color=COLOR_POL[p], width=0.8)\n"
    "    base += tot[p].values\n"
    "pp = ev['polaridad'].value_counts()\n"
    "ax.set_title(f'Los 7 activos — {len(ev):,} eventos (pos {pp[\"positivo\"] / len(ev):.1%} · '\n"
    "             f'neu {pp[\"neutral\"] / len(ev):.1%} · neg {pp[\"negativo\"] / len(ev):.1%})',\n"
    "             fontweight='bold')\n"
    "ax.set_ylabel('eventos (escala propia)')\n"
    "for ax in axes[-2:]:\n"
    "    ax.tick_params(axis='x', labelbottom=True, rotation=45)\n"
    "handles = [plt.Rectangle((0, 0), 1, 1, color=COLOR_POL[p]) for p in POLS]\n"
    "fig.legend(handles, POLS, loc='upper center', ncol=3, bbox_to_anchor=(0.5, 1.01), fontsize=10)\n"
    "fig.suptitle('Eventos relevantes por año, activo y polaridad', fontsize=13, fontweight='bold', y=1.03)\n"
    "plt.tight_layout()\n"
    "plt.show()\n\n"
    "print('Eventos por activo y polaridad:')\n"
    "t2 = ev.pivot_table(index='ticker', columns='polaridad', values='id', aggfunc='size').reindex(index=TICKERS, columns=POLS).fillna(0).astype(int)\n"
    "t2['total'] = t2.sum(axis=1)\n"
    "t2.loc['TOTAL'] = t2.sum()\n"
    "t2",
    "s-07"))

cells.append(md_cell(
    "## 4. Correlación de la señal neta con el retorno por desfase (Figura 13)\n\n"
    "Señal neta del día de un activo = eventos positivos − eventos negativos (en el "
    "panel, ya con el roll-forward de fines de semana al siguiente día hábil). Se "
    "mide la correlación de Spearman entre el **signo** de esa señal y el z-score "
    "del retorno del activo **k días hábiles después** de la fecha de la noticia, "
    "solo en días con señal no nula y con precio propio (sin precio arrastrado):\n\n"
    "- **k = −1**: retorno del día ANTERIOR a la noticia (¿la prensa reporta lo que ya pasó?).\n"
    "- **k = 0**: mismo día (indicio de look-ahead si fuera fuerte; la fecha de "
    "MediaCloud no tiene hora).\n"
    "- **k = +1, +2**: días siguientes. Por el reloj del entorno (observación con "
    "datos hasta e−1, ejecución al cierre de e, retorno de e a e+1), **k = +2 es el "
    "horizonte que el agente puede operar**.\n\n"
    "Barras: los 7 activos agregados, con IC 95% (transformación de Fisher). "
    "Puntos: cada activo por separado. Reproduce `scripts/timing_sentimiento_post_fix.py`.",
    "s-08"))

cells.append(code_cell(
    "p = panel.sort_values(['ticker', 'date']).copy()\n"
    "p['neto'] = (p.n_alto_pos + p.n_resto_pos) - (p.n_alto_neg + p.n_resto_neg)\n"
    "p['z'] = p.groupby('ticker')['ret_1d'].transform(lambda s: (s - s.mean()) / s.std())\n"
    "KS = [-1, 0, 1, 2]\n\n"
    "def corr_k(df, k):\n"
    "    zz = df.groupby('ticker')['z'].shift(-k)\n"
    "    st = df.groupby('ticker')['is_stale'].shift(-k)\n"
    "    m = df['neto'].ne(0) & zz.notna() & (st == 0)\n"
    "    rho, pv = stats.spearmanr(np.sign(df.loc[m, 'neto']), zz[m])\n"
    "    acierto = (np.sign(df.loc[m, 'neto']) == np.sign(zz[m])).mean()\n"
    "    return rho, pv, int(m.sum()), acierto\n\n"
    "agg = pd.DataFrame([dict(zip(['rho', 'p', 'n', 'acierto_signo'], corr_k(p, k)), k=k) for k in KS]).set_index('k')\n"
    "se = 1 / np.sqrt(agg['n'] - 3)\n"
    "agg['ic_bajo'] = np.tanh(np.arctanh(agg['rho']) - 1.96 * se)\n"
    "agg['ic_alto'] = np.tanh(np.arctanh(agg['rho']) + 1.96 * se)\n"
    "por = pd.DataFrame([dict(ticker=t, k=k, rho=corr_k(p[p.ticker == t], k)[0],\n"
    "                         p=corr_k(p[p.ticker == t], k)[1])\n"
    "                    for t in TICKERS for k in KS])\n\n"
    "fig, ax = plt.subplots(figsize=(11, 5.2))\n"
    "x = np.arange(len(KS))\n"
    "col = ['#c0392b' if pv < 0.05 else '#7f8c8d' for pv in agg['p']]\n"
    "ax.bar(x, agg['rho'], color=col, width=0.55, alpha=0.85, zorder=2)\n"
    "ax.errorbar(x, agg['rho'], yerr=[agg['rho'] - agg['ic_bajo'], agg['ic_alto'] - agg['rho']],\n"
    "            fmt='none', ecolor='black', capsize=6, zorder=3)\n"
    "desp = np.linspace(-0.22, 0.22, len(TICKERS))\n"
    "for j, t in enumerate(TICKERS):\n"
    "    s = por[por.ticker == t].set_index('k').reindex(KS)\n"
    "    ax.scatter(x + desp[j], s['rho'], color=COLOR_MAP[t], s=28, zorder=4,\n"
    "               edgecolor='white', linewidth=0.6, label=NOMBRES[t])\n"
    "for xi, (k, r) in zip(x, agg.iterrows()):\n"
    "    ax.text(xi, max(r['ic_alto'], por[por.k == k]['rho'].max()) + 0.02,\n"
    "            f\"ρ={r['rho']:+.3f}\\np={r['p']:.3f}\\nn={int(r['n']):,}\", ha='center', fontsize=8)\n"
    "ax.axhline(0, color='black', lw=0.8)\n"
    "ax.set_xticks(x)\n"
    "ax.set_xticklabels(['k = −1\\n(día anterior)', 'k = 0\\n(mismo día)', 'k = +1', 'k = +2\\n(operable)'])\n"
    "ax.set_ylabel('Spearman: signo de la señal neta vs z del retorno')\n"
    "ax.set_ylim(-0.35, 0.45)\n"
    "ax.set_title('Señal neta de sentimiento vs retorno, por desfase k (7 activos; rojo = p < 0.05)',\n"
    "             fontweight='bold')\n"
    "ax.legend(fontsize=8, ncol=4, loc='lower right')\n"
    "plt.tight_layout()\n"
    "plt.show()\n\n"
    "print('Agregado de los 7 activos:')\n"
    "display(agg.round(4))\n"
    "print('Por activo (rho; * = p < 0.05):')\n"
    "por['celda'] = por.apply(lambda r: f\"{r['rho']:+.3f}{'*' if r['p'] < 0.05 else ''}\", axis=1)\n"
    "por.pivot(index='ticker', columns='k', values='celda').reindex(TICKERS)",
    "s-09"))

cells.append(md_cell(
    "**Lectura.** La única asociación significativa en el agregado es con el retorno "
    "del día ANTERIOR a la noticia (k = −1): la prensa reporta el movimiento más de "
    "lo que lo anticipa (eco, coherente con D19). No hay asociación con el retorno "
    "del mismo día (sin indicio de look-ahead) ni con los horizontes operables "
    "(k = +1, +2). Son 4 desfases x 8 series con n chico por activo: es diagnóstico, "
    "no hallazgo; la prueba de valor del canal es la ablación de R8.",
    "s-10"))

nb = {"nbformat": 4, "nbformat_minor": 5,
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                   "language_info": {"name": "python", "version": "3.14.3"}},
      "cells": cells}
out = Path("notebooks/resultados_sentimiento_R5.ipynb")
out.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Notebook generado: {out}")
