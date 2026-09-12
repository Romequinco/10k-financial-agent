# 10k-financial-agent
LLM agent for financial research on SEC 10-K filings, combining XBRL facts, semantic retrieval, tool routing, and automated evaluation.

Práctica de *LLMs aplicados a Finanzas* (máster MIAX): un agente que responde preguntas sobre los informes 10-K de
seis tecnológicas (NVDA, MSFT, AAPL, GOOGL, META y AMZN; FY2024 y FY2025), cita de dónde sale cada dato y elige bien
entre cuatro herramientas: XBRL exacto, búsqueda en el texto, lectura de una sección entera y listado del corpus. Se
evalúa contra un golden set midiendo calidad, coste y latencia. Enunciado: [docs/00_enunciado.md](docs/00_enunciado.md).

## Grupo

- Óscar Romero Quincoces
- Daniel García López
- Fernando Dapena Tauste

## Estado

12-sep-2026: esqueleto montado. El paquete y los notebooks tienen la estructura, las firmas y los `TODO` de cada paso,
pero todavía no la lógica. Cada `TODO` remite a su guía en `docs/`.

## Estructura

```text
10k-financial-agent/
├── src/agente10k/       código (paquete instalable)
│   ├── config.py        rutas desde la raíz, modelo fijo, clave
│   ├── datos.py         carga y verificación del corpus
│   ├── herramientas.py  las 4 herramientas del contrato
│   ├── retrieval.py     búsqueda densa, BM25 + RRF, reescritura
│   ├── agente.py        RespuestaFinanciera, prompt, agente y responder()
│   ├── guardrails.py    límite de llamadas y verificación XBRL
│   ├── evaluacion.py    golden, evaluadores, evaluar() y tablas
│   └── __main__.py      python -m agente10k preguntas.jsonl
├── notebooks/           un notebook por paso de la práctica (00–08)
├── golden/              golden_propio.jsonl (20 preguntas) y golden_huecos.jsonl
├── resultados/          baseline/, final/, ciegas/ y retrieval/ (se versionan)
├── tests/               test_contratos.py: lo que no se puede cambiar
├── data/                corpus, índice FAISS y ZIP del curso (ver data/README.md)
├── docs/                guías, teoría y pistas de clase (índice en docs/README.md)
├── CLAUDE.md            reglas del repo
├── requirements.txt     versiones fijadas del curso + el propio paquete
└── pyproject.toml
```

## Instalación (Windows, PowerShell)

```powershell
git clone https://github.com/Romequinco/10k-financial-agent.git
cd 10k-financial-agent
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env      # y pegar la clave de OpenRouter en .env
.venv\Scripts\python.exe -m pytest
```

- Probado con Python 3.13.7; vale cualquier versión ≥ 3.12. La primera instalación tarda unos 20–30 minutos y ocupa
  ~1,4 GB, por `torch`, que llega con `sentence-transformers`.
- El entorno debe ir en una ruta corta, como `.venv` dentro del repo. Si no están activadas las rutas largas de
  Windows, pip falla con `OSError` al pasar de 260 caracteres.
- En VS Code se elige el kernel de `.venv`. Desde la terminal hay que usar `.venv\Scripts\python.exe` o activar el
  entorno; si no, Jupyter puede ejecutar los notebooks con el Python del sistema.

## Notebooks

Cada notebook es un paso de la práctica y se ejecuta solo, sin ejecutar antes los anteriores: lee `data/` y lo guardado
en `resultados/`. Los que llaman a la API tienen `EJECUTAR = False` por defecto, así que no gastan ni piden clave hasta
que se cambia.

| Nº | Notebook | Qué se hace | Guía |
| --- | --- | --- | --- |
| 00 | `00_setup_y_datos` | Entorno, integridad del corpus y exploración de los datos | [02](docs/02_datos_corpus_y_xbrl.md) |
| 01 | `01_herramientas` | Las 4 herramientas y sus docstrings | [07](docs/07_skill_herramientas_docstrings.md) |
| 02 | `02_agente_baseline` | Agente con salida estructurada, `responder()`, trayectoria y coste | [08](docs/08_skill_agente_salida_estructurada.md) |
| 03 | `03_golden_set` | Las 20 preguntas propias y su validación | [10](docs/10_skill_golden_set.md) |
| 04 | `04_evaluacion_baseline` | Los 3 evaluadores, `evaluar()` y el baseline congelado | [12](docs/12_skill_evaluadores.md) |
| 05 | `05_mejora_retrieval` | Filtro por metadatos, BM25 + denso y reescritura, con recall@k | [11](docs/11_skill_mejora_retrieval.md) |
| 06 | `06_guardrails` | Límite de llamadas y verificación de cifras contra XBRL | [09](docs/09_skill_guardrails_middleware_xbrl.md) |
| 07 | `07_sistema_final` | Sistema final y tabla baseline frente a final | [13](docs/13_skill_medicion_informe_presentacion.md) |
| 08 | `08_preguntas_ciegas` | Las 10 preguntas ciegas del día 24 | [13 §8](docs/13_skill_medicion_informe_presentacion.md) |

## Uso

```python
from agente10k import responder, evaluar

responder("¿Cuál fue el revenue de NVIDIA en el ejercicio 2025?")   # -> RespuestaFinanciera
evaluar("golden/golden_propio.jsonl")                              # -> resultados/final/
```

Desde la terminal, sin tocar código (así se ejecutarán las preguntas ciegas el día 24):

```powershell
.venv\Scripts\python.exe -m agente10k golden\golden_propio.jsonl --etiqueta baseline --sistema baseline
.venv\Scripts\python.exe -m agente10k ciegas.jsonl --etiqueta ciegas
```

## Qué se versiona

- **Sí:** el código, los notebooks, `golden/`, `resultados/`, `docs/` y `data/`. Los datos se guardan byte a byte
  (`.gitattributes`) para que cuadren los hashes del manifiesto y los offsets de las anclas.
- **No:** `.env` (la clave), `.venv/`, `docs/raw/` (material de clase, transcripciones y repos de terceros) y
  `data/dataset.rar`, que duplica `data/dataset/`.

## Documentación

- [docs/README.md](docs/README.md): índice de la documentación y ruta rápida para la sesión del 17.
- [docs/01_requisitos_y_contratos.md](docs/01_requisitos_y_contratos.md): qué hay que entregar y qué no se puede cambiar.
- [CLAUDE.md](CLAUDE.md): reglas del repo y qué va en cada módulo.
- [data/README.md](data/README.md): los datos y cómo comprobar su integridad.
