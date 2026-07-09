"""Sondeo BVL — dividendos y acciones liberadas por ingeniería inversa (jun-2026).

HALLAZGO (resumen del sondeo, consolidado):
  El MISMO endpoint no documentado de la BVL que ya usamos para precios
  (dataondemand.bvl.com.pe) expone el historial completo de acciones
  corporativas de cada emisor — dividendos en efectivo Y acciones liberadas —
  nativo de la BVL, sin necesidad de terceros (Apify) ni de yfinance.

  Ruta:  GET /v1/issuers/{companyCode}          -> detalle del emisor
         GET /v1/issuers/{companyCode}/value    -> listValue[].listBenefit[]

  El emisor se identifica por un companyCode NUMÉRICO (no el nemónico ni el
  rpjCode). Mapa de identificadores de la BVL (3 sistemas):
     nemonico (CREDITC1)  ->  companyCode (12000)  ->  rpjCode (B80005)
  companyCode se resuelve con GET /v1/issuers (lista de 341 emisores) filtrando
  por companyName, y se confirma con el detalle (listValue trae el nemónico).

  Estructura de cada beneficio (listBenefit):
     benefitType : "DE" = Dividendo en Efectivo | "AL" = Acciones Liberadas
     benefitValue: DE -> monto por acción en `coin`;
                   AL -> % de acciones nuevas   -> ratio de split = 1 + val/100
     coin        : "S/." (PEN) | "US$" (USD)
     dateAgreement (acuerdo JGA) / dateCut (corte ~ ex-date) /
     dateRegistry (registro) / dateDelivery (entrega/pago)

  VALIDACIÓN (CREDITC1): las 13 AL de la BVL reproducen EXACTAMENTE los
  "splits" de yfinance (p.ej. 2010: 14.785 -> 1.14785; 2012: 24.63 -> 1.2463;
  2013: 20.939 -> 1.20939 ...). yfinance es, de hecho, un espejo de esta
  fuente. La diferencia de factor acumulado (5.98 BVL vs 10.36 yfinance) se
  debe solo a 2 splits pre-2010 (2008/2009) fuera del horizonte 2012-2025.

  COBERTURA (todos con datos ~2010 en adelante; horizonte de mercado 2012-2025
  queda cubierto):
     CREDITC1  cc=12000  34 benef  21 DE + 13 AL   S/.
     BUENAVC1  cc=61200  69 benef  69 DE           US$
     ALICORC1  cc=21400  34 benef  34 DE           S/.
     SAGAC1    cc=75700  26 benef  25 DE +  1 AL   S/.
     CORAREC1  cc=20601  86 benef  80 DE +  6 AL   S/.(56) + US$(30)

  Esto resuelve las lagunas documentadas en R3: SAGAC1/CORAREC1 (antes sin
  fuente de ajuste) y BUENAVC1 (antes sin ajuste por ser BVN un ADR USD) ahora
  tienen historial autoritativo de la BVL para el instrumento local en PEN.

  NOTA: el endpoint /v1/corporate-actions ("Hechos de Importancia", POST) NO se
  logró invocar (500 "Regex string must not be null!"); pero eso son avisos
  regulatorios en PDF, no las acciones corporativas que afectan el precio —
  esas están 100% en /v1/issuers/{cc}/value.
"""
from __future__ import annotations

import json
from collections import Counter

import requests

DOD = "https://dataondemand.bvl.com.pe"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": "https://www.bvl.com.pe",
    "Referer": "https://www.bvl.com.pe/",
    "Accept": "application/json, text/plain, */*",
}

# companyCode numérico resuelto y confirmado (nemónico presente en su listValue).
COMPANY_CODE = {
    "CREDITC1": "12000",
    "BUENAVC1": "61200",
    "ALICORC1": "21400",
    "SAGAC1":   "75700",
    "CORAREC1": "20601",
}


def get(path: str) -> object:
    r = requests.get(DOD + path, headers=HEADERS, timeout=40)
    r.raise_for_status()
    return r.json()


def fetch_benefits(company_code: str) -> list[dict]:
    """Devuelve la lista plana de beneficios (dividendos + acciones liberadas)
    de un emisor a partir de /v1/issuers/{companyCode}/value."""
    value = get(f"/v1/issuers/{company_code}/value")
    benefits: list[dict] = []
    for v in value:
        benefits += v.get("listBenefit") or []
    benefits.sort(key=lambda b: b.get("dateCut") or "")
    return benefits


def resolve_company_code(nemonico: str) -> str | None:
    """Resuelve el companyCode numérico de un nemónico recorriendo /v1/issuers
    y confirmando contra el detalle (listValue)."""
    for it in get("/v1/issuers"):
        cc = it.get("companyCode")
        try:
            det = get(f"/v1/issuers/{cc}")
        except Exception:
            continue
        if nemonico in [v.get("nemonico") for v in (det.get("listValue") or [])]:
            return cc
    return None


if __name__ == "__main__":
    summary = {}
    for nemo, cc in COMPANY_CODE.items():
        benefits = fetch_benefits(cc)
        types = Counter(b.get("benefitType") for b in benefits)
        coins = Counter(b.get("coin") for b in benefits)
        cuts = sorted(b["dateCut"] for b in benefits if b.get("dateCut"))
        summary[nemo] = {
            "companyCode": cc, "n": len(benefits),
            "tipos": dict(types), "coin": dict(coins),
            "rango_corte": [cuts[0] if cuts else None, cuts[-1] if cuts else None],
        }
        print(f"{nemo:9} cc={cc}: {len(benefits):3} benef  tipos={dict(types)}  "
              f"coin={dict(coins)}  corte={cuts[0] if cuts else '-'}..{cuts[-1] if cuts else '-'}")

    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
