# Datos de la práctica

Corpus de informes 10-K de la SEC: NVDA, MSFT, AAPL, GOOGL, META y AMZN, ejercicios FY2024 y FY2025, Items 1A, 7, 7A
y 8. Lo reparte el curso y se versiona en el repo para que cualquiera pueda ejecutar el agente en un clon limpio,
sin pasos manuales. La descripción completa, las trampas y la tabla XBRL están en
[docs/02_datos_corpus_y_xbrl.md](../docs/02_datos_corpus_y_xbrl.md).

## Contenido

| Ruta | Qué es | Lo usa |
| --- | --- | --- |
| `corpus/secciones.jsonl` | Texto íntegro de las 48 secciones (empresa × ejercicio × item) | `read_section` |
| `corpus/chunks.jsonl` | Las mismas secciones troceadas en 1.749 fragmentos de ~500 tokens, con `chunk_id` | `search_filings` |
| `corpus/xbrl_facts.parquet` | 135 hechos XBRL, 13 conceptos: la fuente autorizada de cualquier cifra | `get_xbrl_fact` |
| `corpus/indice/` | Índice FAISS (`IndexFlatIP`, `BAAI/bge-small-en-v1.5`, 384 dimensiones) y sus metadatos | `search_filings` |
| `corpus/LEEME.md`, `corpus/MANIFEST.md` | Descripción del corpus, procedencia y SHA-256 de cada fichero | — |
| `dataset/corpus_miax_2026.zip`, `dataset/indice_faiss.zip` | Los dos ZIP originales del curso, de los que sale `corpus/` | Colab o regenerar `corpus/` |
| `dataset/fuentes_10k_html.zip` | Los 12 HTML originales de EDGAR, sin descomprimir. No hacen falta para la práctica | Comprobar la procedencia de una cita |
| `dataset/SHA256SUMS.txt` | SHA-256 de los tres ZIP | Verificación |
| `dataset/celda_descarga.py` | Celda de montaje del notebook de la sesión 1 | Colab |

`corpus/` es el contenido de los dos primeros ZIP ya descomprimido: se puede usar directamente.

## Integridad

Los ficheros se versionan byte a byte: `.gitattributes` desactiva la conversión de finales de línea en `data/`. Si
`chunks.jsonl` o `secciones.jsonl` cambiaran de LF a CRLF, dejarían de cuadrar el hash del manifiesto y los offsets de
carácter de las anclas. Para comprobarlo en un clon:

```python
import hashlib
from pathlib import Path

def sha256(ruta):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()

# Los dos manifiestos declaran el mismo hash de chunks.jsonl
assert sha256("data/corpus/chunks.jsonl") in Path("data/corpus/MANIFEST.md").read_text(encoding="utf-8")
assert sha256("data/corpus/chunks.jsonl") in Path("data/corpus/indice/MANIFEST.md").read_text(encoding="utf-8")
# Los ZIP coinciden con SHA256SUMS.txt
for linea in Path("data/dataset/SHA256SUMS.txt").read_text(encoding="utf-8").split("\n"):
    if linea.strip():
        esperado, nombre = linea.split()
        assert sha256(f"data/dataset/{nombre}") == esperado, nombre
```

## Procedencia

Todo procede de SEC EDGAR: los 10-K son registros públicos presentados ante la Securities and Exchange Commission de
EE. UU. El `MANIFEST.md` del corpus da el CIK, el número de accession y la fecha de cierre de cada presentación, y
cada sección lleva su `url_origen`. El corpus lo empaquetó el curso el 2-sep-2026.

No se versiona `dataset.rar`, el archivo en que se repartió todo esto, porque contiene exactamente los mismos
ficheros que `dataset/`.
