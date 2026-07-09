"""Genera notebooks/exploracion_integracion_bvl.ipynb."""
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
    "# Integración del Dataset Unificado — R6 (5 Empresas BVL)\n\n"
    "Construcción y validación del panel único `(ticker, date)` que combina "
    "mercado + indicadores técnicos (R3), sentimiento de noticias (R5) y "
    "fundamentales trimestrales (R4) sobre el calendario bursátil de la BVL — "
    "el espacio de observación final que verá el agente DRL.\n\n"
    "Para la narrativa completa de las decisiones (qué se decidió, por qué, y "
    "los hallazgos relevantes para la tesis) ver "
    "`docs/hallazgos_integracion_R6.txt`. Este notebook es la evidencia "
    "visual/cuantitativa que sustenta ese documento.\n\n"
    "| Ticker | Empresa | Sector |\n"
    "|--------|---------|--------|\n"
    "| CREDITC1 | Banco de Crédito del Perú | Banca |\n"
    "| BUENAVC1 | Cía. de Minas Buenaventura | Minería |\n"
    "| ALICORC1 | Alicorp | Alimentos |\n"
    "| SAGAC1 | Saga Falabella | Retail |\n"
    "| CORAREC1 | Aceros Arequipa | Manufactura |\n\n"
    "**Decisiones cubiertas en este notebook:**\n"
    "1. Calendario bursátil construido en R6 (no en el entorno DRL, OE1).\n"
    "2. Sentimiento: roll-forward de noticias en día no bursátil + "
    "reagregación, sin decaimiento precalculado (4 columnas crudas).\n"
    "3. Ancla sintética de `days_since_news` en el día 0 de cada activo.\n"
    "4. Fundamentales propagados con `merge_asof` (sin look-ahead).\n"
    "5. Días sin cotización: precio \"stale\" + indicadores recalculados + "
    "bandera `is_no_trade`.\n"
    "6. Corrección de `rsi_14` (bug de fórmula preexistente de R3, no "
    "imputación de datos faltantes).\n"
    "7. Valoración fundamental: P/E y Dividend Yield diarios en el panel "
    "(capitalización / utilidad TTM, y dividendos TTM / precio).",
    "cell-00",
))

# ── Imports y carga ──────────────────────────────────────────────────────────
cells.append(md_cell(
    "## 1. Carga de datos\n\n"
    "Se cargan tanto las fuentes intermedias (mercado y sentimiento por "
    "activo, fundamentales crudos) como el panel final ya construido, para "
    "poder comparar \"antes/después\" de cada decisión de R6 de forma "
    "reproducible en vez de solo narrar los números.",
    "cell-01",
))

cells.append(code_cell(
    "import sys, pathlib\n"
    "sys.path.insert(0, str(pathlib.Path.cwd().parent))\n\n"
    "import pandas as pd\n"
    "import numpy as np\n"
    "import matplotlib.pyplot as plt\n"
    "import seaborn as sns\n"
    "import warnings\n"
    "warnings.filterwarnings('ignore')\n\n"
    "from src.integration.build_dataset import (\n"
    "    build_trading_calendar, _align_sentiment_to_calendar, feature_views,\n"
    ")\n"
    "from src.fundamentals.fundamentals_client import compute_ratios\n"
    "from src.universe import Config\n\n"
    "DATA_INTERIM = pathlib.Path('../data/interim')\n"
    "DATA_RAW = pathlib.Path('../data/raw')\n"
    "DATA_PROCESSED = pathlib.Path('../data/processed')\n\n"
    "TICKERS = ['CREDITC1', 'BUENAVC1', 'ALICORC1', 'SAGAC1', 'CORAREC1']\n"
    "NOMBRES = {\n"
    "    'CREDITC1': 'BCP',\n"
    "    'BUENAVC1': 'Buenaventura',\n"
    "    'ALICORC1': 'Alicorp',\n"
    "    'SAGAC1':   'Saga Falabella',\n"
    "    'CORAREC1': 'Aceros Arequipa',\n"
    "}\n"
    "COLORES = ['#2196F3', '#F44336', '#4CAF50', '#FF9800', '#9C27B0']\n"
    "COLOR_MAP = dict(zip(TICKERS, COLORES))\n\n"
    "sns.set_theme(style='whitegrid', palette='tab10')\n"
    "plt.rcParams.update({'figure.dpi': 110, 'axes.titlesize': 11})\n\n"
    "market = {t: pd.read_parquet(DATA_INTERIM / f'market_{t}.parquet') for t in TICKERS}\n"
    "sentiment_raw = {t: pd.read_parquet(DATA_INTERIM / f'sentiment_{t}.parquet') for t in TICKERS}\n"
    "ASSETS = {a.bvl: a for a in Config.load('../config.yaml').assets}\n"
    "ratios = {t: compute_ratios(pd.read_parquet(DATA_RAW / f'fund_{t}_smv.parquet'), asset=ASSETS[t]) for t in TICKERS}\n"
    "unified = pd.read_parquet(DATA_PROCESSED / 'dataset_unificado.parquet')\n\n"
    "print(f\"Panel unificado: {unified.shape[0]} filas x {unified.shape[1]} columnas\")\n"
    "print(f\"Rango: {unified['date'].min().date()} -> {unified['date'].max().date()}\")\n"
    "print(f\"Activos: {sorted(unified['ticker'].unique())}\")",
    "cell-02",
))

# ── Sección 2: calendario ────────────────────────────────────────────────────
cells.append(md_cell(
    "## 2. Calendario bursátil: construido en R6, no en el entorno (OE1)\n\n"
    "`build_trading_calendar()` toma la UNIÓN de fechas con cotización de "
    "cualquiera de los 5 activos (no el calendario de uno solo) — esa es la "
    "decisión de diseño: el panel define qué días existen como fila, el "
    "entorno DRL solo consume ese índice ya resuelto. Cada activo individual "
    "puede tener menos filas propias (iliquidez, ver sección 6); eso se "
    "refleja como `is_no_trade`, no como un calendario más corto.",
    "cell-03",
))

cells.append(code_cell(
    "cal = build_trading_calendar(pd.concat(market.values(), ignore_index=True))\n"
    "print(f\"Calendario bursátil unificado: {len(cal)} días \"\n"
    "      f\"({cal.min().date()} -> {cal.max().date()})\")\n\n"
    "cal_df = pd.DataFrame([\n"
    "    {'ticker': t, 'empresa': NOMBRES[t], 'filas_propias_R3': len(market[t]),\n"
    "     'dias_calendario_unificado': len(cal),\n"
    "     'huecos_no_trade': len(cal) - len(market[t])}\n"
    "    for t in TICKERS\n"
    "])\n"
    "display(cal_df)",
    "cell-04",
))

# ── Sección 3: sentimiento, roll-forward ─────────────────────────────────────
cells.append(md_cell(
    "## 3. Sentimiento: roll-forward de noticias + reagregación (sin decaimiento)\n\n"
    "Las noticias publicadas en día NO bursátil (fin de semana, feriado BVL) "
    "se asignan al SIGUIENTE día hábil antes de construir el panel — evita "
    "look-ahead (una noticia del sábado no pudo afectar el cierre del "
    "viernes) y recupera cobertura que antes se perdía fuera del calendario. "
    "Si ese día hábil ya tenía noticia propia, se reagregan con media "
    "ponderada por `n_articles` (consistente con `daily_aggregation: mean` "
    "de R5). El panel guarda 4 columnas CRUDAS — `sentiment_score_last`, "
    "`days_since_news`, `has_news`, `n_articles` — sin ningún decaimiento "
    "precalculado: por sugerencia del asesor, la tasa de decaimiento la "
    "aprende el propio agente DRL a partir de `days_since_news`.",
    "cell-05",
))

cells.append(code_cell(
    "rows = []\n"
    "for t in TICKERS:\n"
    "    raw = sentiment_raw[t].copy()\n"
    "    raw['date'] = pd.to_datetime(raw['date'])\n"
    "    en_calendario = raw['date'].isin(cal).sum()\n"
    "    tras_roll = int(unified.loc[unified['ticker'] == t, 'has_news'].sum())\n"
    "    rows.append({\n"
    "        'ticker': t, 'noticias_dias_R5': len(raw),\n"
    "        'dias_ya_en_calendario': en_calendario,\n"
    "        'dias_tras_roll_forward': tras_roll,\n"
    "        '%_cobertura_antes': round(en_calendario / len(cal) * 100, 1),\n"
    "        '%_cobertura_despues': round(tras_roll / len(cal) * 100, 1),\n"
    "    })\n"
    "cov_df = pd.DataFrame(rows)\n"
    "display(cov_df)\n"
    "print(f\"\\nGanancia neta de cobertura por roll-forward: \"\n"
    "      f\"{(cov_df['dias_tras_roll_forward'] - cov_df['dias_ya_en_calendario']).sum()} \"\n"
    "      f\"días-activo recuperados de fin de semana/feriado.\")",
    "cell-06",
))

cells.append(md_cell(
    "**Ejemplo real de colisión y reagregación** — noticia del sábado "
    "2013-07-20 (score 0.0, 2 artículos) se funde con la del lunes nativo "
    "2013-07-22 (score 1.0, 1 artículo). Media ponderada esperada: "
    "`(0.0×2 + 1.0×1) / 3 = 0.333`.",
    "cell-07",
))

cells.append(code_cell(
    "ej = sentiment_raw['CREDITC1'].copy()\n"
    "ej['date'] = pd.to_datetime(ej['date'])\n"
    "print('Crudo (R5), antes de alinear al calendario:')\n"
    "display(ej[(ej['date'] >= '2013-07-19') & (ej['date'] <= '2013-07-23')])\n\n"
    "print('Panel R6, después del roll-forward + reagregación:')\n"
    "display(unified.loc[(unified['ticker'] == 'CREDITC1') & (unified['date'] == '2013-07-22'),\n"
    "                     ['date', 'has_news', 'n_articles', 'sentiment_score_last']])",
    "cell-08",
))

cells.append(md_cell(
    "**`days_since_news`** crece sin tope mientras no hay noticia nueva; la "
    "cola es muy pesada (de cientos de días para los activos con menos "
    "cobertura mediática). Por eso se decidió que el panel guarde el valor "
    "CRUDO y que la transformación `log1p` (no `log` puro, porque "
    "`days_since_news=0` en días con noticia) se aplique en OE1 al construir "
    "la observación del agente, no aquí — mismo principio de separación que "
    "el calendario: R6 guarda crudo, OE1 transforma.",
    "cell-09",
))

cells.append(code_cell(
    "fig, axes = plt.subplots(2, 5, figsize=(20, 6.5))\n"
    "for ax, t in zip(axes[0], TICKERS):\n"
    "    vals = unified.loc[unified['ticker'] == t, 'days_since_news']\n"
    "    ax.hist(vals, bins=40, color=COLOR_MAP[t])\n"
    "    ax.set_title(f'{NOMBRES[t]}\\ndays_since_news (max={vals.max()})', fontsize=9)\n"
    "for ax, t in zip(axes[1], TICKERS):\n"
    "    vals = unified.loc[unified['ticker'] == t, 'days_since_news']\n"
    "    ax.hist(np.log1p(vals), bins=40, color=COLOR_MAP[t])\n"
    "    ax.set_title(f'{NOMBRES[t]}\\nlog1p(days_since_news)', fontsize=9)\n"
    "plt.tight_layout()\n"
    "plt.show()",
    "cell-10",
))

# ── Sección 4: ancla sintética ───────────────────────────────────────────────
cells.append(md_cell(
    "## 4. Ancla sintética en el día 0 (sin NaN antes de la primera noticia)\n\n"
    "Antes de la primera noticia histórica real de un activo, en vez de NaN "
    "se trata el día 0 del panel como si hubiera un evento neutral "
    "(`sentiment_score_last=0`, `days_since_news=0`) — evita inventar un "
    "segundo valor sentinela arbitrario y deja que `days_since_news` crezca "
    "de forma normal desde el inicio del panel.",
    "cell-11",
))

cells.append(code_cell(
    "primeras_filas = (unified.sort_values('date')\n"
    "                  .groupby('ticker').first()\n"
    "                  [['date', 'has_news', 'sentiment_score_last', 'days_since_news']])\n"
    "display(primeras_filas)\n"
    "print('NaN en days_since_news (todo el panel):', unified['days_since_news'].isna().sum())\n"
    "print('NaN en sentiment_score_last (todo el panel):', unified['sentiment_score_last'].isna().sum())",
    "cell-12",
))

# ── Sección 5: fundamentales merge_asof ──────────────────────────────────────
cells.append(md_cell(
    "## 5. Fundamentales: propagación con `merge_asof` (sin look-ahead)\n\n"
    "`pd.merge_asof(..., direction='backward')` sobre `known_date` asigna a "
    "cada día de mercado el ÚLTIMO trimestre que ya era público en esa "
    "fecha — nunca un trimestre futuro. El primer `known_date` de los 5 "
    "activos es 2005-05-15, muy anterior al inicio del horizonte de mercado "
    "(2012-01-02), así que no hay huecos de NaN al inicio del panel.",
    "cell-13",
))

cells.append(code_cell(
    "nan_fund = unified[['roe', 'roa', 'net_margin', 'debt_equity', 'debt_ratio']].isna().sum()\n"
    "print('NaN en ratios fundamentales (todo el panel):')\n"
    "print(nan_fund)\n\n"
    "fig, ax = plt.subplots(figsize=(11, 4))\n"
    "for t in TICKERS:\n"
    "    sub = unified[unified['ticker'] == t]\n"
    "    ax.step(sub['date'], sub['roe'], where='post', label=NOMBRES[t], color=COLOR_MAP[t])\n"
    "ax.set_title('ROE propagado con merge_asof — cada escalón es un nuevo trimestre conocido')\n"
    "ax.legend(ncol=5, fontsize=8)\n"
    "plt.tight_layout()\n"
    "plt.show()",
    "cell-14",
))

cells.append(code_cell(
    "sub = unified[(unified['ticker'] == 'CREDITC1') &\n"
    "              (unified['date'] >= '2019-01-01') & (unified['date'] <= '2021-12-31')]\n"
    "fig, ax = plt.subplots(figsize=(11, 3.5))\n"
    "ax.step(sub['date'], sub['roe'], where='post', color=COLOR_MAP['CREDITC1'])\n"
    "ax.set_title('CREDITC1 — zoom 2019-2021: escalones trimestrales de ROE (forward-fill desde known_date)')\n"
    "plt.tight_layout()\n"
    "plt.show()",
    "cell-15",
))

# ── Sección 5b: valoración P/E y DY ──────────────────────────────────────────
cells.append(md_cell(
    "## 5b. Valoración fundamental: P/E y Dividend Yield\n\n"
    "P/E y DY son las únicas señales fundamentales que NO se propagan tal cual "
    "desde R4: se calculan a nivel DIARIO en el panel porque combinan el precio "
    "diario (R3) con insumos trimestrales (R4) y los dividendos (R3).\n\n"
    "- **P/E** = `close_raw × acciones_en_circulación / UtilidadNeta_TTM` = "
    "capitalización / utilidad TTM. Se usa `close_raw` (no `close_split_adj`): "
    "es invariante a splits y evita mezclar bases de acciones. Es NaN cuando la "
    "utilidad TTM ≤ 0 (años de pérdida) — ausencia SEMÁNTICA, no hueco de datos.\n"
    "- **DY** = dividendos por acción TTM (PEN) / `close_raw`.\n\n"
    "Las acciones en circulación se reconstruyen de la SMV "
    "(`(Capital Emitido − tesorería) / nominal`), con el `quantity` de la BVL "
    "como ancla/validación y el Form 20-F de la SEC para BUENAVC1 (capital en "
    "USD sin nominal limpio). Metodología y validación completas: "
    "`docs/pipeline_extraccion_datos.txt` §3.10.2 y "
    "`docs/hallazgos_fundamentales_R4.txt` §5.9.",
    "cell-15b",
))

cells.append(code_cell(
    "cov = []\n"
    "for t in TICKERS:\n"
    "    g = unified[unified['ticker'] == t]\n"
    "    cov.append({'ticker': t, 'empresa': NOMBRES[t],\n"
    "                'pe_no_nan_%': round(g['pe'].notna().mean() * 100, 1),\n"
    "                'pe_mediana': round(g['pe'].median(), 1),\n"
    "                'dy_no_nan_%': round(g['dy'].notna().mean() * 100, 1),\n"
    "                'dy_mediana_%': round(g['dy'].median() * 100, 2)})\n"
    "print('Cobertura de P/E (NaN = años de pérdida) y DY en el panel:')\n"
    "display(pd.DataFrame(cov))\n\n"
    "fig, (axpe, axdy) = plt.subplots(2, 1, figsize=(13, 8), sharex=True)\n"
    "for t in TICKERS:\n"
    "    g = unified[unified['ticker'] == t].sort_values('date')\n"
    "    axpe.plot(g['date'], g['pe'].clip(lower=0, upper=60),\n"
    "              color=COLOR_MAP[t], lw=1.0, label=NOMBRES[t])\n"
    "    axdy.plot(g['date'], g['dy'] * 100, color=COLOR_MAP[t], lw=1.0, label=NOMBRES[t])\n"
    "axpe.set_title('P/E diario (recortado a [0, 60] para visualización; NaN en años de pérdida)')\n"
    "axpe.set_ylabel('P/E (×)'); axpe.legend(ncol=5, fontsize=8)\n"
    "axdy.set_title('Dividend Yield diario (%) — dividendo TTM por acción / close_raw')\n"
    "axdy.set_ylabel('DY (%)')\n"
    "plt.tight_layout(); plt.show()",
    "cell-15c",
))

cells.append(code_cell(
    "# P/E integra precio DIARIO (R3) con EPS TRIMESTRAL (R4): se mueve a diario\n"
    "# dentro del trimestre y salta cuando entra un nuevo known_date (merge_asof).\n"
    "sub = unified[(unified['ticker'] == 'CREDITC1') &\n"
    "              (unified['date'] >= '2019-01-01') & (unified['date'] <= '2021-12-31')].sort_values('date')\n"
    "fig, ax = plt.subplots(figsize=(12, 4))\n"
    "ax.plot(sub['date'], sub['pe'], color=COLOR_MAP['CREDITC1'], lw=1.3, label='P/E (diario)')\n"
    "ax2 = ax.twinx()\n"
    "ax2.step(sub['date'], sub['eps_ttm'], where='post', color='#777', lw=1.2, ls='--',\n"
    "         label='EPS TTM (escalón trimestral)')\n"
    "ax.set_title('CREDITC1 2019-2021 — P/E diario = precio diario (R3) / EPS TTM escalonado (R4)')\n"
    "ax.set_ylabel('P/E (×)'); ax2.set_ylabel('EPS TTM (S/ por acción)')\n"
    "l1, lb1 = ax.get_legend_handles_labels(); l2, lb2 = ax2.get_legend_handles_labels()\n"
    "ax.legend(l1 + l2, lb1 + lb2, fontsize=8, loc='best')\n"
    "plt.tight_layout(); plt.show()",
    "cell-15d",
))

# ── Sección 6: días sin cotización ───────────────────────────────────────────
cells.append(md_cell(
    "## 6. Días sin cotización (`is_no_trade`): precio stale, no imputación de OHLCV\n\n"
    "Al reindexar sobre el calendario común, los activos de baja liquidez "
    "quedan con filas sin cotización propia. Se arrastra el último "
    "`close_total_return` conocido y se RECALCULAN los indicadores técnicos "
    "sobre la serie ya completa (`technical_indicators.add_indicators`) en "
    "vez de arrastrar a ciegas los valores de los indicadores — así "
    "`ret_1d=0` y `volatility_20` decaen correctamente durante el tramo sin "
    "operación. No se completa open/high/low/volumen: esa ruta ya se "
    "descartó explícitamente (ver `docs/justificacion_cierre_vs_ohlcv.txt` — "
    "el agente solo usa `close_total_return`).",
    "cell-16",
))

cells.append(code_cell(
    "def episodios(mask):\n"
    "    grp = (mask != mask.shift()).cumsum()\n"
    "    return mask[mask].groupby(grp[mask]).size()\n\n"
    "rows = []\n"
    "for t in TICKERS:\n"
    "    sub = unified[unified['ticker'] == t].sort_values('date')\n"
    "    mask = sub['is_no_trade'].astype(bool)\n"
    "    runs = episodios(mask)\n"
    "    rows.append({\n"
    "        'ticker': t, 'dias_no_trade': int(mask.sum()), 'episodios': len(runs),\n"
    "        'racha_max_sesiones': int(runs.max()) if len(runs) else 0,\n"
    "    })\n"
    "display(pd.DataFrame(rows))",
    "cell-17",
))

cells.append(code_cell(
    "sub = unified[(unified['ticker'] == 'SAGAC1') &\n"
    "              (unified['date'] >= '2012-08-15') & (unified['date'] <= '2012-09-25')]\n"
    "fig, ax = plt.subplots(figsize=(11, 4))\n"
    "ax.plot(sub['date'], sub['close_total_return'], marker='o', color=COLOR_MAP['SAGAC1'])\n"
    "for _, r in sub[sub['is_no_trade'] == 1].iterrows():\n"
    "    ax.axvspan(r['date'], r['date'] + pd.Timedelta(days=1), color='red', alpha=0.15)\n"
    "ax.set_title('SAGAC1 — racha de 4 sesiones sin operar (rojo): precio stale, '\n"
    "             'salto real al reanudar el 2012-09-10 (-3.4%)')\n"
    "plt.tight_layout()\n"
    "plt.show()",
    "cell-18",
))

# ── Sección 7: RSI fix ───────────────────────────────────────────────────────
cells.append(md_cell(
    "## 7. Corrección de `rsi_14`: bug de fórmula preexistente, no imputación\n\n"
    "Al validar quedó expuesto que `rsi_14` ya tenía **27.5% de NaN en los "
    "parquets originales de R3**, independiente de los días `is_no_trade` de "
    "esta sesión. Causa: la fórmula original hacía `loss.replace(0, np.nan)` "
    "— cuando una ventana de 14 días no tenía ninguna pérdida, el RSI "
    "quedaba indefinido en vez de calcularse. Esto NO es un hueco de datos "
    "(el precio, el delta diario, la ganancia y la pérdida de cada ventana "
    "son 100% reales y observados) — es un caso límite de la fórmula mal "
    "manejado. Se corrigió con dos reglas explícitas:\n"
    "- pérdida=0, ganancia>0 → RSI=100 (límite exacto de la fórmula de "
    "Wilder, igual que TA-Lib/pandas-ta — sin ambigüedad).\n"
    "- pérdida=0, ganancia=0 (ventana totalmente plana, 0/0 verdaderamente "
    "indefinido) → RSI=50 (convención \"sin señal de momentum\", no 100, "
    "porque ahí no hubo movimiento real — coherente con que esos tramos ya "
    "están marcados `is_no_trade`).\n\n"
    "La celda siguiente reproduce la fórmula ANTERIOR (ya corregida en "
    "`src/market/technical_indicators.py`) solo para esta comparación.",
    "cell-19",
))

cells.append(code_cell(
    "def rsi_formula_anterior(close, window=14):\n"
    "    delta = close.diff()\n"
    "    gain = delta.clip(lower=0).rolling(window).mean()\n"
    "    loss = (-delta.clip(upper=0)).rolling(window).mean()\n"
    "    rs = gain / loss.replace(0, np.nan)\n"
    "    return 100 - (100 / (1 + rs))\n\n"
    "rows = []\n"
    "for t in TICKERS:\n"
    "    m = market[t].sort_values('date')\n"
    "    nan_antes = rsi_formula_anterior(m['close_total_return']).isna().sum()\n"
    "    nan_despues = m['rsi_14'].isna().sum()\n"
    "    rows.append({\n"
    "        'ticker': t, 'filas': len(m),\n"
    "        'NaN_formula_anterior': int(nan_antes), '%_anterior': round(nan_antes / len(m) * 100, 1),\n"
    "        'NaN_formula_corregida': int(nan_despues), '%_corregida': round(nan_despues / len(m) * 100, 1),\n"
    "    })\n"
    "display(pd.DataFrame(rows))",
    "cell-20",
))

cells.append(code_cell(
    "print('RSI == 100 (sin pérdidas, con ganancia):', int((unified['rsi_14'] == 100).sum()))\n"
    "print('RSI == 50  (ventana totalmente plana)   :', int((unified['rsi_14'] == 50).sum()))\n\n"
    "sub = unified[(unified['ticker'] == 'SAGAC1') &\n"
    "              (unified['date'] >= '2012-08-30') & (unified['date'] <= '2012-09-12')]\n"
    "display(sub[['date', 'close_total_return', 'is_no_trade', 'rsi_14']])",
    "cell-21",
))

# ── Sección 8: vistas de señales ─────────────────────────────────────────────
cells.append(md_cell(
    "## 8. Vistas de señales para los experimentos DRL (R8)\n\n"
    "Las 4 configuraciones de señales que pide R8 NO son datasets separados: "
    "son selecciones de columnas sobre este mismo panel único.",
    "cell-22",
))

cells.append(code_cell(
    "views = feature_views(unified)\n"
    "for name, cols in views.items():\n"
    "    print(f\"{name} ({len(cols)} columnas):\")\n"
    "    print(f\"  {cols}\\n\")",
    "cell-23",
))

# ── Sección 9: síntesis ──────────────────────────────────────────────────────
cells.append(md_cell(
    "## 9. Síntesis final",
    "cell-24",
))

cells.append(code_cell(
    "print('=' * 64)\n"
    "print('SÍNTESIS R6 — DATASET UNIFICADO')\n"
    "print('=' * 64)\n"
    "print(f\"Panel: {unified.shape[0]} filas x {unified.shape[1]} columnas\")\n"
    "print(f\"Activos: {unified['ticker'].nunique()} | \"\n"
    "      f\"Calendario: {len(cal)} días ({cal.min().date()} -> {cal.max().date()})\")\n"
    "cov = unified.groupby('ticker')['has_news'].mean() * 100\n"
    "print(f\"Cobertura de sentimiento tras roll-forward: {cov.min():.1f}% (SAGAC1) \"\n"
    "      f\"a {cov.max():.1f}% (CREDITC1), promedio {cov.mean():.1f}%\")\n"
    "print(f\"Días is_no_trade: {int(unified['is_no_trade'].sum())} \"\n"
    "      f\"({unified['is_no_trade'].mean() * 100:.2f}% del panel)\")\n"
    "print('NaN en columnas clave: ' + ', '.join(\n"
    "    f\"{c}={unified[c].isna().sum()}\"\n"
    "    for c in ['sentiment_score_last', 'days_since_news', 'has_news', 'n_articles',\n"
    "              'roe', 'roa', 'rsi_14', 'close_total_return']\n"
    "))",
    "cell-25",
))

# ── Construir y escribir ─────────────────────────────────────────────────────
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

out = Path("notebooks/exploracion_integracion_bvl.ipynb")
out.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Notebook generado: {out}")
