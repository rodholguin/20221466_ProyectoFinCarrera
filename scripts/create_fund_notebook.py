"""Genera notebooks/exploracion_fundamentales_bvl.ipynb."""
import json
from pathlib import Path


def code_cell(source: str, cell_id: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "id": cell_id,
        "metadata": {},
        "outputs": [],
        "source": source,
    }


def md_cell(source: str, cell_id: str) -> dict:
    return {
        "cell_type": "markdown",
        "id": cell_id,
        "metadata": {},
        "source": source,
    }


cells = []

# ── Título ───────────────────────────────────────────────────────────────────
cells.append(md_cell(
    "# Exploración de Datos Fundamentales — 5 Empresas BVL\n\n"
    "Visualización del pipeline R4: indicadores fundamentales trimestrales obtenidos\n"
    "del web service SOAP de Datos Abiertos de la SMV (2020-Q1 a 2023-Q4).\n\n"
    "| Ticker | Empresa | Sector | Moneda |\n"
    "|--------|---------|--------|--------|\n"
    "| CREDITC1 | Banco de Crédito del Perú | Banca | PEN |\n"
    "| BUENAVC1 | Cía. de Minas Buenaventura | Minería | USD |\n"
    "| ALICORC1 | Alicorp | Alimentos | PEN |\n"
    "| SAGAC1 | Saga Falabella | Retail | PEN |\n"
    "| CORAREC1 | Aceros Arequipa | Manufactura | PEN |\n\n"
    "> **Nota metodológica:** Los montos están en **miles** de la unidad monetaria "
    "(`value` = miles de PEN o miles de USD). `known_date` es la fecha de publicación "
    "efectiva (cierre del trimestre + 45 días de lag conservador), usada para evitar "
    "*look-ahead bias* al entrenar el modelo DRL.",
    "cell-00",
))

# ── Imports ───────────────────────────────────────────────────────────────────
cells.append(code_cell(
    "import sys, pathlib\n"
    "sys.path.insert(0, str(pathlib.Path.cwd().parent))\n\n"
    "import pandas as pd\n"
    "import matplotlib.pyplot as plt\n"
    "import matplotlib.dates as mdates\n"
    "import seaborn as sns\n"
    "import numpy as np\n"
    "import warnings\n"
    "warnings.filterwarnings('ignore')\n\n"
    "DATA_RAW = pathlib.Path('../data/raw')\n\n"
    "TICKERS = ['CREDITC1', 'BUENAVC1', 'ALICORC1', 'SAGAC1', 'CORAREC1']\n"
    "NOMBRES = {\n"
    "    'CREDITC1': 'BCP',\n"
    "    'BUENAVC1': 'Buenaventura',\n"
    "    'ALICORC1': 'Alicorp',\n"
    "    'SAGAC1':   'Saga Falabella',\n"
    "    'CORAREC1': 'Aceros Arequipa',\n"
    "}\n"
    "SECTORES = {\n"
    "    'CREDITC1': 'Banca',\n"
    "    'BUENAVC1': 'Minería (USD)',\n"
    "    'ALICORC1': 'Alimentos',\n"
    "    'SAGAC1':   'Retail',\n"
    "    'CORAREC1': 'Manufactura',\n"
    "}\n"
    "COLORES = ['#2196F3', '#F44336', '#4CAF50', '#FF9800', '#9C27B0']\n"
    "COLOR_MAP = dict(zip(TICKERS, COLORES))\n\n"
    "sns.set_theme(style='whitegrid', palette='tab10')\n"
    "plt.rcParams.update({'figure.dpi': 110, 'axes.titlesize': 11})",
    "cell-01",
))

# ── Sección 1 ─────────────────────────────────────────────────────────────────
cells.append(md_cell("## 1. Carga de datos", "cell-02"))

cells.append(code_cell(
    "from src.fundamentals.fundamentals_client import compute_ratios\n\n"
    "fund = {}\n"
    "for ticker in TICKERS:\n"
    "    p = DATA_RAW / f'fund_{ticker}_smv.parquet'\n"
    "    if p.exists():\n"
    "        fund[ticker] = pd.read_parquet(p)\n"
    "        df_t = fund[ticker]\n"
    "        print(f'✓ {ticker}: {len(df_t)} filas, '\n"
    "              f'{df_t[\"period\"].nunique()} periodos, '\n"
    "              f'moneda={df_t[\"currency\"].unique().tolist()}')\n"
    "    else:\n"
    "        print(f'✗ {ticker}: no encontrado — ejecutar scripts/gen_fundamentals.py')\n\n"
    "all_fund = pd.concat(list(fund.values()), ignore_index=True)\n"
    "all_fund['period'] = pd.to_datetime(all_fund['period'])\n\n"
    "ratios = compute_ratios(all_fund)\n"
    "ratios['period'] = pd.to_datetime(ratios['period'])\n"
    "print(f'\\nRatios calculados: {len(ratios)} filas')",
    "cell-03",
))

# ── Sección 2 ─────────────────────────────────────────────────────────────────
cells.append(md_cell("## 2. Resumen estadístico", "cell-04"))

cells.append(code_cell(
    "resumen = []\n"
    "for ticker, df in fund.items():\n"
    "    r = ratios[ratios['ticker'] == ticker]\n"
    "    resumen.append({\n"
    "        'Ticker':   ticker,\n"
    "        'Empresa':  NOMBRES[ticker],\n"
    "        'Sector':   SECTORES[ticker],\n"
    "        'Periodos': df['period'].nunique(),\n"
    "        'Desde':    df['period'].min(),\n"
    "        'Hasta':    df['period'].max(),\n"
    "        'Cuentas':  df['account'].nunique(),\n"
    "        'Moneda':   df['currency'].iloc[0],\n"
    "        'ROE (ult)': r['roe'].iloc[-1].round(4) if len(r) else None,\n"
    "        'ROA (ult)': r['roa'].iloc[-1].round(4) if len(r) else None,\n"
    "    })\n\n"
    "df_res = pd.DataFrame(resumen).set_index('Ticker')\n"
    "df_res",
    "cell-05",
))

# ── Sección 3 ─────────────────────────────────────────────────────────────────
cells.append(md_cell(
    "## 3. Estructura del Balance — Activo, Pasivo y Patrimonio\n\n"
    "Las barras apiladas muestran cómo se financia el activo total "
    "(pasivo en rojo, patrimonio en azul). La línea discontinua confirma que "
    "Activo = Pasivo + Patrimonio (identidad contable).\n\n"
    "> **BCP** es un banco: su ratio D/E estructuralmente alto (~7-9×) es normal "
    "en la industria financiera (los depósitos son pasivo). No es comparable "
    "directamente con las empresas no financieras.",
    "cell-06",
))

cells.append(code_cell(
    "fig, axes = plt.subplots(3, 2, figsize=(14, 14), constrained_layout=True)\n"
    "axes_flat = axes.flatten()\n"
    "fig.suptitle('Estructura del Balance (miles de unidad monetaria) — SMV 2020-2023',\n"
    "             fontsize=13, fontweight='bold')\n\n"
    "for i, ticker in enumerate(TICKERS):\n"
    "    ax = axes_flat[i]\n"
    "    df = fund.get(ticker)\n"
    "    if df is None:\n"
    "        ax.set_visible(False)\n"
    "        continue\n"
    "    sub = df[df['account'].isin(\n"
    "        ['INFO_ActivoTotal', 'INFO_PasivoTotal', 'INFO_PatrimonioTotal'])].copy()\n"
    "    sub['period'] = pd.to_datetime(sub['period'])\n"
    "    pivot = sub.pivot_table(\n"
    "        index='period', columns='account', values='value', aggfunc='first'\n"
    "    ).sort_index()\n"
    "    labels_x = [f\"{p.year}Q{(p.month-1)//3+1}\" for p in pivot.index]\n"
    "    pivot_k = pivot / 1_000\n"
    "    moneda = df['currency'].iloc[0]\n\n"
    "    col_pas = 'INFO_PasivoTotal'\n"
    "    col_pat = 'INFO_PatrimonioTotal'\n"
    "    col_act = 'INFO_ActivoTotal'\n"
    "    x = np.arange(len(pivot_k))\n\n"
    "    if col_pas in pivot_k.columns:\n"
    "        ax.bar(x, pivot_k[col_pas], label='Pasivo', color='#EF5350', alpha=0.85, width=0.7)\n"
    "    bot = pivot_k.get(col_pas, pd.Series(0, index=pivot_k.index))\n"
    "    if col_pat in pivot_k.columns:\n"
    "        ax.bar(x, pivot_k[col_pat], bottom=bot, label='Patrimonio',\n"
    "               color='#42A5F5', alpha=0.85, width=0.7)\n"
    "    if col_act in pivot_k.columns:\n"
    "        ax.plot(x, pivot_k[col_act], 'k--o', linewidth=1.5,\n"
    "                markersize=4, label='Activo Total', zorder=5)\n\n"
    "    ax.set_xticks(x[::2])\n"
    "    ax.set_xticklabels(labels_x[::2], rotation=40, fontsize=8)\n"
    "    ax.set_title(f'{ticker} — {NOMBRES[ticker]} ({moneda})',\n"
    "                 fontweight='bold', color=COLOR_MAP[ticker])\n"
    "    ax.set_ylabel(f'Miles {moneda}')\n"
    "    ax.legend(fontsize=8, loc='upper left')\n"
    "    ax.yaxis.set_major_formatter(\n"
    "        plt.FuncFormatter(lambda v, _: f'{v:,.0f}'))\n\n"
    "axes_flat[-1].set_visible(False)\n"
    "plt.show()",
    "cell-07",
))

# ── Sección 4 ─────────────────────────────────────────────────────────────────
cells.append(md_cell(
    "## 4. Cuenta de Resultados — Ingresos y Utilidad Neta\n\n"
    "Los valores son **acumulados del ejercicio (YTD)** tal como los reporta la SMV, "
    "por lo que Q4 (diciembre) es el valor anual completo y Q1 es el más pequeño.\n\n"
    "> Buenaventura reporta en **USD**. Su utilidad puede ser negativa en años de bajo "
    "precio del oro o por deterioro de activos.",
    "cell-08",
))

cells.append(code_cell(
    "fig, axes = plt.subplots(3, 2, figsize=(14, 14), constrained_layout=True)\n"
    "axes_flat = axes.flatten()\n"
    "fig.suptitle('Ingresos y Utilidad Neta (miles de unidad monetaria, YTD) — SMV 2020-2023',\n"
    "             fontsize=13, fontweight='bold')\n\n"
    "for i, ticker in enumerate(TICKERS):\n"
    "    ax = axes_flat[i]\n"
    "    df = fund.get(ticker)\n"
    "    if df is None:\n"
    "        ax.set_visible(False)\n"
    "        continue\n"
    "    sub = df[df['account'].isin(\n"
    "        ['INFO_TotalIngreso', 'INFO_UtilidadNeta'])].copy()\n"
    "    sub['period'] = pd.to_datetime(sub['period'])\n"
    "    pivot = sub.pivot_table(\n"
    "        index='period', columns='account', values='value', aggfunc='first'\n"
    "    ).sort_index() / 1_000\n"
    "    labels_x = [f\"{p.year}Q{(p.month-1)//3+1}\" for p in pivot.index]\n"
    "    moneda = df['currency'].iloc[0]\n"
    "    x = np.arange(len(pivot))\n\n"
    "    ax2 = ax.twinx()\n"
    "    if 'INFO_TotalIngreso' in pivot.columns:\n"
    "        ax.bar(x, pivot['INFO_TotalIngreso'], color='#78909C',\n"
    "               alpha=0.55, width=0.7, label='Ingresos')\n"
    "    if 'INFO_UtilidadNeta' in pivot.columns:\n"
    "        colors_bar = ['#43A047' if v >= 0 else '#E53935'\n"
    "                      for v in pivot['INFO_UtilidadNeta']]\n"
    "        ax2.bar(x + 0.0, pivot['INFO_UtilidadNeta'], color=colors_bar,\n"
    "                alpha=0.85, width=0.35, label='Utilidad Neta')\n"
    "        ax2.axhline(0, color='black', linewidth=0.5, linestyle=':')\n\n"
    "    ax.set_xticks(x[::2])\n"
    "    ax.set_xticklabels(labels_x[::2], rotation=40, fontsize=8)\n"
    "    ax.set_title(f'{ticker} — {NOMBRES[ticker]} ({moneda})',\n"
    "                 fontweight='bold', color=COLOR_MAP[ticker])\n"
    "    ax.set_ylabel(f'Ingresos (miles {moneda})', color='#546E7A')\n"
    "    ax2.set_ylabel(f'Utilidad Neta (miles {moneda})', color='#388E3C')\n"
    "    lines1, lab1 = ax.get_legend_handles_labels()\n"
    "    lines2, lab2 = ax2.get_legend_handles_labels()\n"
    "    ax.legend(lines1 + lines2, lab1 + lab2, fontsize=8, loc='upper left')\n"
    "    ax.yaxis.set_major_formatter(\n"
    "        plt.FuncFormatter(lambda v, _: f'{v:,.0f}'))\n"
    "    ax2.yaxis.set_major_formatter(\n"
    "        plt.FuncFormatter(lambda v, _: f'{v:,.0f}'))\n\n"
    "axes_flat[-1].set_visible(False)\n"
    "plt.show()",
    "cell-09",
))

# ── Sección 5 ─────────────────────────────────────────────────────────────────
cells.append(md_cell(
    "## 5. Ratios fundamentales — Evolución temporal\n\n"
    "Ratios calculados directamente de `INFO_*` del SMV (no requieren número de acciones):\n\n"
    "| Ratio | Fórmula | Interpretación |\n"
    "|-------|---------|----------------|\n"
    "| **ROE** | Utilidad Neta / Patrimonio | Rentabilidad sobre fondos propios |\n"
    "| **ROA** | Utilidad Neta / Activo Total | Rentabilidad sobre activos |\n"
    "| **Margen Neto** | Utilidad Neta / Total Ingresos | Eficiencia de conversión ventas→utilidad |\n"
    "| **D/E** | Pasivo / Patrimonio | Apalancamiento financiero |\n"
    "| **Debt Ratio** | Pasivo / Activo | Proporción de activos financiados con deuda |",
    "cell-10",
))

cells.append(code_cell(
    "ultimo_q = ratios.groupby('ticker').last().reset_index()[[\n"
    "    'ticker', 'period', 'roe', 'roa', 'net_margin', 'debt_equity', 'debt_ratio'\n"
    "]]\n"
    "ultimo_q['period'] = ultimo_q['period'].dt.strftime('%Y-%m-%d')\n"
    "ultimo_q = ultimo_q.set_index('ticker')\n"
    "ultimo_q.columns.name = None\n\n"
    "fmt = {'roe': '{:.2%}', 'roa': '{:.2%}', 'net_margin': '{:.2%}',\n"
    "       'debt_equity': '{:.2f}×', 'debt_ratio': '{:.2%}'}\n\n"
    "print('Ratios — último período disponible:')\n"
    "ultimo_q.style.format({\n"
    "    'roe':         '{:.2%}',\n"
    "    'roa':         '{:.2%}',\n"
    "    'net_margin':  '{:.2%}',\n"
    "    'debt_equity': '{:.2f}',\n"
    "    'debt_ratio':  '{:.2%}',\n"
    "})",
    "cell-11",
))

cells.append(code_cell(
    "RATIO_META = [\n"
    "    ('roe',         'ROE (Utilidad/Patrimonio)',    '{:.1%}',  None),\n"
    "    ('roa',         'ROA (Utilidad/Activo)',        '{:.1%}',  None),\n"
    "    ('net_margin',  'Margen Neto (Util./Ingresos)', '{:.1%}',  (-1.0, 1.5)),\n"
    "    ('debt_ratio',  'Debt Ratio (Pasivo/Activo)',   '{:.0%}',  None),\n"
    "]\n\n"
    "fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)\n"
    "axes_flat = axes.flatten()\n"
    "fig.suptitle('Ratios Fundamentales — Evolución Trimestral (2020-2023)',\n"
    "             fontsize=13, fontweight='bold')\n\n"
    "for ax, (col, title, fmt_str, ylim) in zip(axes_flat, RATIO_META):\n"
    "    for ticker, color in zip(TICKERS, COLORES):\n"
    "        sub = ratios[ratios['ticker'] == ticker].sort_values('period')\n"
    "        if sub.empty or col not in sub.columns:\n"
    "            continue\n"
    "        ax.plot(sub['period'], sub[col],\n"
    "                label=f'{ticker} ({NOMBRES[ticker]})',\n"
    "                color=color, linewidth=1.5, marker='o', markersize=4)\n"
    "    ax.axhline(0, color='black', linewidth=0.6, linestyle=':')\n"
    "    ax.set_title(title, fontweight='bold')\n"
    "    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))\n"
    "    ax.xaxis.set_major_locator(mdates.YearLocator())\n"
    "    ax.yaxis.set_major_formatter(plt.FuncFormatter(\n"
    "        lambda v, _: fmt_str.format(v)))\n"
    "    if ylim:\n"
    "        ax.set_ylim(*ylim)\n"
    "    ax.legend(fontsize=8, loc='best')\n"
    "    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30)\n\n"
    "plt.show()",
    "cell-12",
))

# ── Sección 6 ─────────────────────────────────────────────────────────────────
cells.append(md_cell(
    "## 6. Comparativa entre empresas — Último trimestre (2023-Q4)\n\n"
    "Comparación side-by-side de ratios para el último período disponible.\n"
    "BUENAVC1 se muestra con moneda diferente (USD); los ratios son adimensionales "
    "y por tanto comparables entre monedas.",
    "cell-13",
))

cells.append(code_cell(
    "ult = ratios[ratios['period'] == ratios['period'].max()].set_index('ticker')\n\n"
    "ratios_plot = ['roe', 'roa', 'net_margin', 'debt_ratio']\n"
    "labels_plot = ['ROE', 'ROA', 'Margen Neto', 'Debt Ratio']\n\n"
    "fig, axes = plt.subplots(1, len(ratios_plot), figsize=(14, 5), constrained_layout=True)\n"
    "fig.suptitle(f'Comparativa de Ratios — {ult[\"period\"].iloc[0].strftime(\"%Y-Q4\")}',\n"
    "             fontsize=13, fontweight='bold')\n\n"
    "for ax, col, label in zip(axes, ratios_plot, labels_plot):\n"
    "    vals = [ult.loc[t, col] if t in ult.index else np.nan for t in TICKERS]\n"
    "    bar_colors = [COLOR_MAP[t] for t in TICKERS]\n"
    "    bars = ax.bar(range(len(TICKERS)), vals, color=bar_colors, alpha=0.85, width=0.6)\n"
    "    ax.axhline(0, color='black', linewidth=0.6, linestyle=':')\n"
    "    ax.set_title(label, fontweight='bold')\n"
    "    ax.set_xticks(range(len(TICKERS)))\n"
    "    ax.set_xticklabels([NOMBRES[t] for t in TICKERS], rotation=35,\n"
    "                       ha='right', fontsize=9)\n"
    "    for bar, val in zip(bars, vals):\n"
    "        if np.isfinite(val):\n"
    "            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),\n"
    "                    f'{val:.1%}', ha='center', va='bottom', fontsize=8)\n"
    "    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:.0%}'))\n\n"
    "plt.show()",
    "cell-14",
))

# ── Sección 7 ─────────────────────────────────────────────────────────────────
cells.append(md_cell(
    "## 7. Heatmap de ratios — todas las empresas × todos los períodos",
    "cell-15",
))

cells.append(code_cell(
    "for col, title in [('roe', 'ROE'), ('roa', 'ROA'),\n"
    "                   ('net_margin', 'Margen Neto'), ('debt_ratio', 'Debt Ratio')]:\n"
    "    pivot_heat = ratios.pivot_table(\n"
    "        index='ticker', columns='period', values=col, aggfunc='first')\n"
    "    pivot_heat.columns = [\n"
    "        f\"{p.year}Q{(p.month-1)//3+1}\" for p in pivot_heat.columns]\n\n"
    "    fig, ax = plt.subplots(figsize=(16, 3))\n"
    "    sns.heatmap(pivot_heat * 100, annot=True, fmt='.1f',\n"
    "                cmap='RdYlGn', center=0,\n"
    "                linewidths=0.4, ax=ax, cbar_kws={'label': '%'})\n"
    "    ax.set_title(f'{title} por empresa y trimestre (%)', fontweight='bold')\n"
    "    ax.set_xlabel('')\n"
    "    ax.set_ylabel('')\n"
    "    plt.xticks(rotation=40, fontsize=8)\n"
    "    plt.tight_layout()\n"
    "    plt.show()",
    "cell-16",
))

# ── Sección 8 ─────────────────────────────────────────────────────────────────
cells.append(md_cell(
    "## 8. Vista de datos crudos (formato largo)\n\n"
    "Muestra las primeras filas de cada parquet en el esquema canónico `FUNDAMENTALS_SCHEMA`.",
    "cell-17",
))

cells.append(code_cell(
    "for ticker, df in fund.items():\n"
    "    print(f'\\n=== {ticker} ({NOMBRES[ticker]}) — {len(df)} filas ===')\n"
    "    info_rows = df[df['account'].str.startswith('INFO_')].copy()\n"
    "    info_rows['period'] = pd.to_datetime(info_rows['period'])\n"
    "    info_rows = info_rows.sort_values('period')\n"
    "    display(info_rows.tail(10))",
    "cell-18",
))

# ── Construir y escribir ───────────────────────────────────────────────────────
nb = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.14.3",
        },
    },
    "cells": cells,
}

out = Path("notebooks/exploracion_fundamentales_bvl.ipynb")
out.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Notebook generado: {out}")
