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
    "# Exploración de Datos Fundamentales — 7 Empresas BVL (universo vigente)\n\n"
    "Visualización del pipeline R4: indicadores fundamentales trimestrales obtenidos\n"
    "del web service SOAP de Datos Abiertos de la SMV (2005-Q1 a 2025-Q4). Incluye\n"
    "acciones en circulación, EPS TTM y los ratios de valoración **P/E** y **DY**\n"
    "(ver secciones 5b y docs/pipeline §3.10.2).\n\n"
    "| Ticker | Empresa | Sector | Moneda |\n"
    "|--------|---------|--------|--------|\n"
    "| CREDITC1 | Banco de Crédito del Perú | Banca (plan de cuentas SBS) | PEN |\n"
    "| ALICORC1 | Alicorp | Alimentos | PEN (2025-Q4 en USD) |\n"
    "| INRETC1 | InRetail Peru Corp | Retail / farmacias (EEFF consolidados) | PEN |\n"
    "| CPACASC1 | Cementos Pacasmayo | Construcción | PEN |\n"
    "| FERREYC1 | Ferreycorp | Bienes de capital | PEN |\n"
    "| LUSURC1 | Luz del Sur | Electricidad | PEN |\n"
    "| MINSURI1 | Minsur | Minería (estaño/cobre) | USD desde 2012 |\n\n"
    "> **Nota metodológica:** Los montos están en **miles** de la unidad monetaria "
    "(`value` = miles de PEN o miles de USD). `known_date` es la fecha de publicación "
    "efectiva: la fecha REAL del hecho de importancia en la BVL cuando existe y, si no, "
    "un lag de respaldo calibrado por activo (D20; bandera `known_date_real`). Evita "
    "*look-ahead bias* al entrenar el modelo DRL. En los gráficos de MONTOS se excluyen "
    "los trimestres reportados en una moneda distinta de la predominante del activo "
    "(Minsur: PEN antes de 2012; Alicorp: 2025-Q4 en USD); los ratios no se afectan.",
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
    "TICKERS = ['CREDITC1', 'ALICORC1', 'INRETC1', 'CPACASC1', 'FERREYC1', 'LUSURC1', 'MINSURI1']\n"
    "NOMBRES = {\n"
    "    'CREDITC1': 'BCP',\n"
    "    'ALICORC1': 'Alicorp',\n"
    "    'INRETC1':  'InRetail',\n"
    "    'CPACASC1': 'Pacasmayo',\n"
    "    'FERREYC1': 'Ferreycorp',\n"
    "    'LUSURC1':  'Luz del Sur',\n"
    "    'MINSURI1': 'Minsur',\n"
    "}\n"
    "SECTORES = {\n"
    "    'CREDITC1': 'Banca',\n"
    "    'ALICORC1': 'Alimentos',\n"
    "    'INRETC1':  'Retail/farmacias',\n"
    "    'CPACASC1': 'Construcción',\n"
    "    'FERREYC1': 'Bienes de capital',\n"
    "    'LUSURC1':  'Electricidad',\n"
    "    'MINSURI1': 'Minería (USD)',\n"
    "}\n"
    "COLORES = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2']\n"
    "COLOR_MAP = dict(zip(TICKERS, COLORES))\n"
    "# Advertencias de datos que se muestran en los títulos (ver la nota de la sección 5).\n"
    "NOTAS = {'FERREYC1': ' [individual de holding desde 2012]'}\n\n"
    "sns.set_theme(style='whitegrid', palette='tab10')\n"
    "plt.rcParams.update({'figure.dpi': 110, 'axes.titlesize': 11})",
    "cell-01",
))

# ── Sección 1 ─────────────────────────────────────────────────────────────────
cells.append(md_cell("## 1. Carga de datos", "cell-02"))

cells.append(code_cell(
    "from src.fundamentals.fundamentals_client import compute_ratios\n"
    "# Las rutas del cliente de R4 son relativas a la raíz del repo; el notebook corre\n"
    "# desde notebooks/. Sin esto el conteo híbrido de acciones (Informe Bursátil\n"
    "# Mensual de la BVL) no se encuentra y se cae al capital del balance.\n"
    "import src.fundamentals.fundamentals_client as _fc\n"
    "_fc._BVL_MENSUAL_CACHE = pathlib.Path('../data/interim/bvl_mensual.parquet')\n"
    "from src.universe import Config\n\n"
    "ASSETS = {a.bvl: a for a in Config.load('../config.yaml').assets}\n\n"
    "fund, ratio_list = {}, []\n"
    "for ticker in TICKERS:\n"
    "    p = DATA_RAW / f'fund_{ticker}_smv.parquet'\n"
    "    if p.exists():\n"
    "        fund[ticker] = pd.read_parquet(p)\n"
    "        df_t = fund[ticker]\n"
    "        # asset=... añade shares_outstanding, net_income_ttm y eps_ttm (insumos P/E)\n"
    "        ratio_list.append(compute_ratios(df_t, asset=ASSETS[ticker]))\n"
    "        print(f'✓ {ticker}: {len(df_t)} filas, '\n"
    "              f'{df_t[\"period\"].nunique()} periodos, '\n"
    "              f'moneda={df_t[\"currency\"].unique().tolist()}')\n"
    "    else:\n"
    "        print(f'✗ {ticker}: no encontrado — ejecutar scripts/fetch_fund_extended.py')\n\n"
    "def montos_moneda_principal(df):\n"
    "    \"\"\"Filas en la moneda predominante del activo (para graficar MONTOS).\"\"\"\n"
    "    cur = df.groupby('period')['currency'].first()\n"
    "    principal = cur.mode().iloc[0]\n"
    "    fuera = cur[cur != principal]\n"
    "    return df[~df['period'].isin(fuera.index)], principal, len(fuera)\n\n"
    "all_fund = pd.concat(list(fund.values()), ignore_index=True)\n"
    "all_fund['period'] = pd.to_datetime(all_fund['period'])\n\n"
    "ratios = pd.concat(ratio_list, ignore_index=True)\n"
    "ratios['period'] = pd.to_datetime(ratios['period'])\n"
    "print(f'\\nRatios calculados: {len(ratios)} filas, columnas={list(ratios.columns)}')",
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
    "fig, axes = plt.subplots(4, 2, figsize=(15, 19), constrained_layout=True)\n"
    "axes_flat = axes.flatten()\n"
    "fig.suptitle('Estructura del Balance (millones de unidad monetaria) — SMV 2005-2025',\n"
    "             fontsize=13, fontweight='bold')\n\n"
    "for i, ticker in enumerate(TICKERS):\n"
    "    ax = axes_flat[i]\n"
    "    df = fund.get(ticker)\n"
    "    if df is None:\n"
    "        ax.set_visible(False)\n"
    "        continue\n"
    "    df, moneda, n_fuera = montos_moneda_principal(df)\n"
    "    sub = df[df['account'].isin(\n"
    "        ['INFO_ActivoTotal', 'INFO_PasivoTotal', 'INFO_PatrimonioTotal'])].copy()\n"
    "    sub['period'] = pd.to_datetime(sub['period'])\n"
    "    pivot = sub.pivot_table(\n"
    "        index='period', columns='account', values='value', aggfunc='first'\n"
    "    ).sort_index()\n"
    "    labels_x = [f\"{p.year}Q{(p.month-1)//3+1}\" for p in pivot.index]\n"
    "    pivot_k = pivot / 1_000\n\n"
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
    "    ax.set_xticks(x[::4])\n"
    "    ax.set_xticklabels(labels_x[::4], rotation=40, fontsize=8)\n"
    "    nota = f' — excluye {n_fuera} trim. en otra moneda' if n_fuera else ''\n"
    "    ax.set_title(f'{ticker} — {NOMBRES[ticker]} (millones {moneda}){nota}{NOTAS.get(ticker, \"\")}',\n"
    "                 fontweight='bold', color=COLOR_MAP[ticker], fontsize=10)\n"
    "    ax.set_ylabel(f'Millones {moneda}')\n"
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
    "> Minsur reporta en **USD** desde 2012 (pérdidas en 2015 y 2017). InRetail "
    "reporta desde su salida a bolsa (2012-Q3) y se usan sus estados CONSOLIDADOS.",
    "cell-08",
))

cells.append(code_cell(
    "fig, axes = plt.subplots(4, 2, figsize=(15, 19), constrained_layout=True)\n"
    "axes_flat = axes.flatten()\n"
    "fig.suptitle('Ingresos y Utilidad Neta (millones de unidad monetaria, YTD) — SMV 2005-2025',\n"
    "             fontsize=13, fontweight='bold')\n\n"
    "for i, ticker in enumerate(TICKERS):\n"
    "    ax = axes_flat[i]\n"
    "    df = fund.get(ticker)\n"
    "    if df is None:\n"
    "        ax.set_visible(False)\n"
    "        continue\n"
    "    df, moneda, n_fuera = montos_moneda_principal(df)\n"
    "    sub = df[df['account'].isin(\n"
    "        ['INFO_TotalIngreso', 'INFO_UtilidadNeta'])].copy()\n"
    "    sub['period'] = pd.to_datetime(sub['period'])\n"
    "    pivot = sub.pivot_table(\n"
    "        index='period', columns='account', values='value', aggfunc='first'\n"
    "    ).sort_index() / 1_000\n"
    "    labels_x = [f\"{p.year}Q{(p.month-1)//3+1}\" for p in pivot.index]\n"
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
    "    ax.set_xticks(x[::4])\n"
    "    ax.set_xticklabels(labels_x[::4], rotation=40, fontsize=8)\n"
    "    nota = f' — excluye {n_fuera} trim. en otra moneda' if n_fuera else ''\n"
    "    ax.set_title(f'{ticker} — {NOMBRES[ticker]} (millones {moneda}){nota}{NOTAS.get(ticker, \"\")}',\n"
    "                 fontweight='bold', color=COLOR_MAP[ticker], fontsize=10)\n"
    "    ax.set_ylabel(f'Ingresos (millones {moneda})', color='#546E7A')\n"
    "    ax2.set_ylabel(f'Utilidad Neta (millones {moneda})', color='#388E3C')\n"
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
    "| **Debt Ratio** | Pasivo / Activo | Proporción de activos financiados con deuda |\n\n"
    "> **ADVERTENCIA DE DATOS (detectada el 2026-10-06): FERREYCORP.** Desde 2012 "
    "Ferreycorp S.A.A. es un HOLDING (Ferreyros pasó a ser subsidiaria) y R4 usa su "
    "estado INDIVIDUAL, que solo refleja la matriz: ingresos de apenas 1-6% de los "
    "consolidados y pasivo/activo de 0.05 contra 0.59 consolidado (2023-Q4). La utilidad "
    "neta coincide (método de participación), así que ROE, EPS y P/E son válidos, pero "
    "**margen neto, ROA, D/E y debt ratio de FERREYC1 posteriores a 2011 no son "
    "comparables**. Es el mismo caso que InRetail, que ya usa el consolidado. "
    "Pendiente de decisión: pasar FERREYC1 a `smv_tipo: C`.",
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
    "fig, axes = plt.subplots(2, 2, figsize=(15, 10), constrained_layout=True)\n"
    "axes_flat = axes.flatten()\n"
    "fig.suptitle('Ratios Fundamentales — Evolución Trimestral (2005-2025)',\n"
    "             fontsize=13, fontweight='bold')\n\n"
    "for ax, (col, title, fmt_str, ylim) in zip(axes_flat, RATIO_META):\n"
    "    for ticker, color in zip(TICKERS, COLORES):\n"
    "        sub = ratios[ratios['ticker'] == ticker].sort_values('period')\n"
    "        if sub.empty or col not in sub.columns:\n"
    "            continue\n"
    "        ax.plot(sub['period'], sub[col],\n"
    "                label=f'{ticker} ({NOMBRES[ticker]})',\n"
    "                color=color, linewidth=1.3)\n"
    "    ax.axhline(0, color='black', linewidth=0.6, linestyle=':')\n"
    "    ax.set_title(title, fontweight='bold')\n"
    "    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))\n"
    "    ax.xaxis.set_major_locator(mdates.YearLocator(2))\n"
    "    ax.yaxis.set_major_formatter(plt.FuncFormatter(\n"
    "        lambda v, _: fmt_str.format(v)))\n"
    "    if ylim:\n"
    "        ax.set_ylim(*ylim)\n"
    "    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30)\n"
    "handles, labels = axes_flat[0].get_legend_handles_labels()\n"
    "fig.legend(handles, labels, loc='lower center', ncol=4, fontsize=9,\n"
    "           bbox_to_anchor=(0.5, -0.04))\n\n"
    "plt.show()",
    "cell-12",
))

# ── Sección 5b ────────────────────────────────────────────────────────────────
cells.append(md_cell(
    "## 5b. Acciones en circulación, EPS TTM y valoración (P/E, DY)\n\n"
    "Serie histórica de **acciones en circulación** reconstruida como "
    "`(Capital Emitido − Acciones en Cartera) / valor nominal` (SMV), con el "
    "`quantity` de la BVL como ancla y validación (coinciden al dígito en 4/5) y el "
    "conteo HÍBRIDO vigente: acciones emitidas según el Informe Bursátil Mensual de la "
    "BVL menos la tesorería de la SMV; InRetail por tramos oficiales (holding sin "
    "nominal) y Minsur con el total económico constante (acción de inversión = 1/3 "
    "del patrimonio). A partir de ahí:\n\n"
    "- **P/E** = `close_raw × acciones / UtilidadNeta_TTM` = capitalización / utilidad "
    "TTM (invariante a splits; se usa `close_raw`, no `close_split_adj`).\n"
    "- **DY** = dividendos por acción TTM (PEN, fuente BVL R3) / `close_raw`.\n\n"
    "P/E y DY son ratios **diarios** y viven en el panel unificado R6 "
    "(`data/processed/dataset_unificado.parquet`); aquí se grafican desde ese panel. "
    "Metodología y validación: docs/pipeline §3.10.2, hallazgos R4 §5.9.",
    "cell-12b",
))

cells.append(code_cell(
    "# Acciones en circulación reconstruidas (trimestral)\n"
    "fig, axes = plt.subplots(4, 2, figsize=(14, 15), constrained_layout=True)\n"
    "axf = axes.flatten()\n"
    "fig.suptitle('Acciones en circulación = (Capital Emitido − tesorería) / nominal (SMV)',\n"
    "             fontsize=13, fontweight='bold')\n"
    "for i, ticker in enumerate(TICKERS):\n"
    "    ax = axf[i]\n"
    "    s = ratios[ratios['ticker'] == ticker].sort_values('period')\n"
    "    if s.empty or 'shares_outstanding' not in s.columns:\n"
    "        ax.set_visible(False); continue\n"
    "    ax.plot(s['period'], s['shares_outstanding'] / 1e6,\n"
    "            color=COLOR_MAP[ticker], linewidth=1.8, marker='o', markersize=3)\n"
    "    ax.set_title(f'{ticker} — {NOMBRES[ticker]}', fontweight='bold', color=COLOR_MAP[ticker])\n"
    "    ax.set_ylabel('Millones de acciones')\n"
    "    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:,.0f}'))\n"
    "axf[-1].set_visible(False)\n"
    "plt.show()",
    "cell-12c",
))

cells.append(code_cell(
    "# P/E y DY diarios desde el panel unificado R6\n"
    "panel = pd.read_parquet('../data/processed/dataset_unificado.parquet')\n"
    "fig, (axpe, axdy) = plt.subplots(2, 1, figsize=(14, 9), constrained_layout=True)\n"
    "fig.suptitle('Valoración diaria — P/E y Dividend Yield (panel R6, 2012-2025)',\n"
    "             fontsize=13, fontweight='bold')\n"
    "for ticker in TICKERS:\n"
    "    g = panel[panel['ticker'] == ticker].sort_values('date')\n"
    "    if g.empty:\n"
    "        continue\n"
    "    axpe.plot(g['date'], g['pe'].clip(lower=0, upper=60),\n"
    "              label=f'{ticker} ({NOMBRES[ticker]})', color=COLOR_MAP[ticker], linewidth=1.0)\n"
    "    axdy.plot(g['date'], g['dy'] * 100,\n"
    "              label=f'{ticker} ({NOMBRES[ticker]})', color=COLOR_MAP[ticker], linewidth=1.0)\n"
    "axpe.set_title('P/E (recortado a [0, 60]; NaN en años de pérdida)', fontweight='bold')\n"
    "axpe.set_ylabel('P/E (×)')\n"
    "axpe.legend(fontsize=8, ncol=4, loc='upper center')\n"
    "axdy.set_title('Dividend Yield (%) — dividendo TTM por acción / close_raw', fontweight='bold')\n"
    "axdy.set_ylabel('DY (%)')\n"
    "axdy.legend(fontsize=8, ncol=4, loc='upper center')\n"
    "for ax in (axpe, axdy):\n"
    "    ax.xaxis.set_major_locator(mdates.YearLocator(2))\n"
    "    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))\n"
    "plt.show()",
    "cell-12d",
))

# ── Sección 6 ─────────────────────────────────────────────────────────────────
cells.append(md_cell(
    "## 6. Comparativa entre empresas — Último trimestre disponible\n\n"
    "Comparación side-by-side de ratios para el último período disponible.\n"
    "Minsur reporta en USD (y Alicorp en USD en 2025-Q4); los ratios son adimensionales "
    "y por tanto comparables entre monedas. El banco (BCP) tiene un debt ratio "
    "estructuralmente alto porque sus depósitos son pasivo.",
    "cell-13",
))

cells.append(code_cell(
    "ult = ratios[ratios['period'] == ratios['period'].max()].set_index('ticker')\n\n"
    "ratios_plot = ['roe', 'roa', 'net_margin', 'debt_ratio']\n"
    "labels_plot = ['ROE', 'ROA', 'Margen Neto', 'Debt Ratio']\n\n"
    "fig, axes = plt.subplots(1, len(ratios_plot), figsize=(17, 5.5), constrained_layout=True)\n"
    "_p = ult['period'].iloc[0]\n"
    "fig.suptitle(f'Comparativa de Ratios — {_p.year}-Q{(_p.month - 1) // 3 + 1}',\n"
    "             fontsize=13, fontweight='bold')\n\n"
    "for ax, col, label in zip(axes, ratios_plot, labels_plot):\n"
    "    vals_real = [ult.loc[t, col] if t in ult.index else np.nan for t in TICKERS]\n"
    "    vals = [min(v, 1.0) if col == 'net_margin' else v for v in vals_real]\n"
    "    bar_colors = [COLOR_MAP[t] for t in TICKERS]\n"
    "    bars = ax.bar(range(len(TICKERS)), vals, color=bar_colors, alpha=0.85, width=0.6)\n"
    "    ax.axhline(0, color='black', linewidth=0.6, linestyle=':')\n"
    "    ax.set_title(label, fontweight='bold')\n"
    "    ax.set_xticks(range(len(TICKERS)))\n"
    "    ax.set_xticklabels([NOMBRES[t] for t in TICKERS], rotation=35,\n"
    "                       ha='right', fontsize=9)\n"
    "    for bar, val, real in zip(bars, vals, vals_real):\n"
    "        if np.isfinite(val):\n"
    "            txt = f'{real:.1%}' + ('\\n(recortado)' if real != val else '')\n"
    "            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),\n"
    "                    txt, ha='center', va='bottom' if val >= 0 else 'top', fontsize=8)\n"
    "    ax.set_xticklabels([NOMBRES[t] + ('*' if t in NOTAS and col != 'roe' else '') for t in TICKERS],\n"
    "                       rotation=35, ha='right', fontsize=9)\n"
    "    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:.0%}'))\n\n"
    "fig.text(0.01, -0.04, '* Ferreycorp: estado individual de holding; margen, ROA y debt ratio '\n"
    "         'no comparables (ver la advertencia de la sección 5).', fontsize=9)\n"
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
    "    fig, ax = plt.subplots(figsize=(22, 4))\n"
    "    sns.heatmap(pivot_heat * 100, annot=False,\n"
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
