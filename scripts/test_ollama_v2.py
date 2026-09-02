"""Una sola llamada al LLM con el prompt v2, para medir latencia y validar el
formato antes de comprometer una corrida larga."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.sentiment.llm_sentiment import classify_article

CASOS = [
    ("Alicorp firma acuerdo para adquirir el 60% de Inka Crops", "Alicorp"),
    ("Aceros Arequipa paraliza la produccion en su fabrica principal", "Aceros Arequipa"),
    ("BCP y su plan de inversion en agencias para el 2025", "Banco de Credito del Peru"),
    ("Indecopi suprime derechos antidumping contra alambron chino", "Aceros Arequipa"),
    ("Teleton Peru celebro a empresas que ayudaron a la recaudacion", "Alicorp"),
]

modelo = sys.argv[1] if len(sys.argv) > 1 else "gemma3:4b"
print(f"Modelo: {modelo}\n")
for titulo, empresa in CASOS:
    t0 = time.time()
    try:
        r = classify_article(titulo, empresa, model=modelo, timeout=300)
        dt = time.time() - t0
        print(f"  {dt:>6.1f}s  {r['categoria']:<24} pol={str(r['polaridad']):<9} "
              f"<- {titulo[:52]}")
    except Exception as e:
        print(f"  ERROR tras {time.time()-t0:.1f}s: {type(e).__name__}: {e}")
        break
