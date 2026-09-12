# 10k-financial-agent
LLM agent for financial research on SEC 10-K filings, combining XBRL facts, semantic retrieval, tool routing, and automated evaluation.

Práctica de *LLMs aplicados a Finanzas* (máster MIAX): un agente que responde preguntas sobre los informes 10-K de
seis tecnológicas (NVDA, MSFT, AAPL, GOOGL, META y AMZN; FY2024 y FY2025), cita de dónde sale cada dato y elige bien
entre cuatro herramientas: XBRL exacto, búsqueda en el texto, lectura de una sección entera y listado del corpus. Se
evalúa contra un golden set midiendo calidad, coste y latencia. Enunciado: [docs/00_enunciado.md](docs/00_enunciado.md).

## Contenido del repo

| Carpeta | Qué hay |
| --- | --- |
| [`docs/`](docs/README.md) | Enunciado, requisitos y contratos, teoría, *skills* (guías paso a paso con código), pistas de clase, guías de los repos de referencia y glosario. Se empieza por [docs/README.md](docs/README.md) |
| [`data/`](data/README.md) | Corpus de la práctica: secciones, fragmentos, hechos XBRL, índice FAISS y los ZIP originales del curso |

El código del agente, las herramientas, los evaluadores y el golden set se añadirán más adelante.

## Qué se versiona

- **Sí:** `docs/` y `data/`. Los datos se guardan byte a byte (`.gitattributes`) para que cuadren los hashes del
  manifiesto y los offsets de las anclas.
- **No:** `docs/raw/`, con el material de clase, las transcripciones, los repos de terceros y las notas de trabajo, y
  `data/dataset.rar`, que duplica `data/dataset/`.

## Por dónde empezar

1. [docs/01_requisitos_y_contratos.md](docs/01_requisitos_y_contratos.md): qué hay que entregar, qué no se puede cambiar y fechas.
2. [docs/README.md](docs/README.md): índice de la documentación y ruta rápida para la sesión del 17 de septiembre.
3. [data/README.md](data/README.md): qué datos hay y cómo comprobar su integridad.
