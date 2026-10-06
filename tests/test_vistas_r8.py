"""Tests de las vistas de la ablación de R8 (D6 enmendada, D27).

POR QUÉ ESTE ARCHIVO EXISTE. La ablación de R8 compara brazos que solo deben
diferir en QUÉ CANAL entra. Cualquier diferencia SISTEMÁTICA entre brazos que no
sea el canal —macro colado en tres vistas, una escala distinta, una columna que
se repite— hace que el resultado sea inatribuible, y el criterio de abandono de
D11 convierte eso en un error caro: si el canal de sentimiento no supera al
baseline, EL CANAL NO SE TOMA. Una ablación sesgada mata un canal que servía, o
salva uno que no.

Ya pasó dos veces, así que acá quedan las guardas:

  1. `mercado_sentimiento` y `mercado_fundamentales` llevaban MACRO adentro
     (corregido el 2026-09-12; entrada #3 de inconsistencias).
  2. `sue_*` y `pico_sue_*` escapaban a la winsorización de ±5σ y entraban al
     agente con valores de hasta -22.46, cuatro veces el rango del resto
     (corregido el 2026-09-18; ver D27).

Los tests de acá son BARATOS y CORREN CONTRA EL PANEL REAL: si no está
construido, se saltan.

    python tests/test_vistas_r8.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.env.features import (
    GROUPS,
    PASSTHROUGH,
    PASSTHROUGH_PREFIJOS,
    VIEWS,
    VISTAS_ABLACION,
    WINSOR_SIGMA,
    build_features,
)
from src.env.panel import DEFAULT_PANEL, load_panel

WARMUP = 250
_cache: dict[str, object] = {}


def _panel(view: str):
    if view not in _cache:
        _cache[view] = load_panel(view=view, warmup=WARMUP)
    return _cache[view]


def _hay_panel() -> bool:
    return Path(DEFAULT_PANEL).exists()


# --------------------------------------------------------------------------
# 1. escala: NINGUNA feature sale del rango de D6
# --------------------------------------------------------------------------
def test_ninguna_feature_excede_la_winsorizacion_de_D6():
    """La guarda de D27. Un solo canal fuera de escala confunde la ablación."""
    if not _hay_panel():
        print("  (saltado: no existe el panel de R6)")
        return
    culpables = []
    for v in VIEWS:
        p = _panel(v)
        f = p.features.values[WARMUP:]
        fuera = np.abs(f) > WINSOR_SIGMA + 1e-5
        if fuera.any():
            for j in np.unique(np.where(fuera)[2]):
                culpables.append(
                    f"{v}/{p.features.columns[j]} "
                    f"(min {f[:, :, j].min():.2f}, max {f[:, :, j].max():.2f})"
                )
    assert not culpables, (
        "features fuera de ±5σ, o sea con hasta varias veces el rango de las "
        "demás: " + "; ".join(sorted(set(culpables)))
    )


def test_las_binarias_no_fueron_dañadas_por_el_recorte():
    """El recorte de D27 debe ser la IDENTIDAD sobre las columnas 0/1."""
    if not _hay_panel():
        print("  (saltado: no existe el panel de R6)")
        return
    p = _panel("completa")
    binarias = [c for c in p.features.columns if c in PASSTHROUGH]
    assert binarias, "la vista completa debería traer columnas de PASSTHROUGH"
    for c in binarias:
        j = p.features.columns.index(c)
        x = p.features.values[WARMUP:, :, j]
        valores = np.unique(x)
        assert valores.min() >= 0.0 and valores.max() <= 1.0, (
            f"{c} salió de [0, 1] tras el recorte: {valores.min()}..{valores.max()}"
        )


def test_la_sorpresa_conserva_magnitud_dentro_del_rango():
    """Winsorizar NO puede haber aplastado la sorpresa a una binaria: el punto
    del acta §B3 es que la MAGNITUD informa, y eso tiene que sobrevivir."""
    if not _hay_panel():
        print("  (saltado: no existe el panel de R6)")
        return
    p = _panel("mercado_fundamentales")
    sue = [c for c in p.features.columns if c.startswith("sue_") and c != "sue_valido"]
    assert sue, "no hay columnas de sorpresa en la vista fundamental"
    for c in sue:
        j = p.features.columns.index(c)
        x = p.features.values[WARMUP:, :, j].ravel()
        distintos = len(np.unique(np.round(x, 4)))
        assert distintos > 50, f"{c} quedó con solo {distintos} valores distintos"
        assert x.std() > 0.1, f"{c} quedó casi constante (std {x.std():.4f})"


# --------------------------------------------------------------------------
# 2. atribución: cada brazo añade UN canal y nada más
# --------------------------------------------------------------------------
def test_cada_brazo_de_la_ablacion_agrega_exactamente_un_canal():
    """La guarda de la entrada #3. Se verifica sobre la DEFINICIÓN, sin panel."""
    base = set(VIEWS["solo_mercado"])
    assert base == {"mercado"}
    for v in VISTAS_ABLACION:
        grupos = set(VIEWS[v])
        extra = grupos - base
        assert grupos >= base, f"{v} no contiene la base de mercado"
        assert len(extra) <= 1, (
            f"{v} agrega {sorted(extra)} sobre solo_mercado: son {len(extra)} "
            "canales y la ablación le atribuiría a uno el aporte de todos"
        )


def test_las_vistas_de_ablacion_no_llevan_macro_escondido():
    if not _hay_panel():
        print("  (saltado: no existe el panel de R6)")
        return
    for v in ("mercado_sentimiento", "mercado_fundamentales"):
        cols = _panel(v).features.columns
        macro = [c for c in cols if c.startswith("macro_")]
        assert not macro, (
            f"{v} trae columnas macro ({macro}): comparar contra solo_mercado "
            "mediría dos canales y se lo atribuiría a uno"
        )


def test_los_brazos_son_anidados_sobre_la_base():
    """Todo brazo debe CONTENER las columnas de solo_mercado, en el mismo orden.
    Si la base cambiara entre brazos, la diferencia ya no sería el canal."""
    if not _hay_panel():
        print("  (saltado: no existe el panel de R6)")
        return
    base = _panel("solo_mercado").features.columns
    for v in VISTAS_ABLACION:
        cols = _panel(v).features.columns
        assert cols[: len(base)] == base, (
            f"{v} no arranca con las mismas columnas de mercado: {cols[:len(base)]}"
        )


def test_la_vista_completa_es_la_union_de_los_brazos():
    if not _hay_panel():
        print("  (saltado: no existe el panel de R6)")
        return
    union: list[str] = []
    for v in VISTAS_ABLACION:
        for c in _panel(v).features.columns:
            if c not in union:
                union.append(c)
    completa = _panel("completa").features.columns
    assert set(completa) == set(union), (
        "la vista completa no es la unión de los brazos: "
        f"sobran {sorted(set(completa) - set(union))}, "
        f"faltan {sorted(set(union) - set(completa))}"
    )


def test_ninguna_vista_repite_columnas():
    if not _hay_panel():
        print("  (saltado: no existe el panel de R6)")
        return
    for v in VIEWS:
        cols = _panel(v).features.columns
        assert len(cols) == len(set(cols)), f"{v} repite columnas"


# --------------------------------------------------------------------------
# 3. el canal fundamental tiene señal, no ceros
# --------------------------------------------------------------------------
def test_el_canal_fundamental_no_esta_vacio():
    """Un canal todo-ceros pasaría la ablación como 'no aporta' sin haber
    aportado nunca nada que medir. Es el fallo silencioso que hay que atrapar."""
    if not _hay_panel():
        print("  (saltado: no existe el panel de R6)")
        return
    base = set(_panel("solo_mercado").features.columns)
    p = _panel("mercado_fundamentales")
    propias = [c for c in p.features.columns if c not in base]
    assert len(propias) >= 20, f"solo {len(propias)} columnas fundamentales"

    muertas = []
    for c in propias:
        j = p.features.columns.index(c)
        x = p.features.values[WARMUP:, :, j]
        # `pico_sue_*` es ralo A PROPÓSITO (solo el primer día bursátil desde la
        # publicación), así que se le pide que dispare, no que esté siempre.
        umbral = 0.005 if c.startswith("pico_sue_") else 0.20
        if np.mean(x != 0.0) < umbral:
            muertas.append(f"{c} ({np.mean(x != 0.0):.2%} no-cero)")
    assert not muertas, "columnas fundamentales sin señal: " + ", ".join(muertas)


def test_las_dimensiones_de_observacion_son_las_declaradas():
    """Si una vista cambia de tamaño sin que nadie lo note, las corridas viejas
    del registro dejan de ser comparables con las nuevas."""
    if not _hay_panel():
        print("  (saltado: no existe el panel de R6)")
        return
    esperado = {
        "solo_mercado": 11,
        "mercado_macro": 18,
        "mercado_sentimiento": 24,
        "mercado_fundamentales": 33,
        "completa": 53,
    }
    for v, n in esperado.items():
        real = len(_panel(v).features.columns)
        assert real == n, (
            f"{v} tiene {real} columnas por activo y el documento declara {n}. "
            "Si el cambio es deliberado, hay que actualizar la tabla de la "
            "sección 2 de docs/resultados_entorno_OE1.txt y este test."
        )


# --------------------------------------------------------------------------
if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(list(globals().items())):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {nombre}")
            except AssertionError as exc:
                fallos += 1
                print(f"FALLA {nombre}: {exc}")
            except Exception as exc:  # noqa: BLE001
                fallos += 1
                print(f"ERROR {nombre}: {type(exc).__name__}: {exc}")
    print("\n" + ("todos los tests pasaron" if not fallos else f"{fallos} test(s) con problemas"))
    sys.exit(1 if fallos else 0)
