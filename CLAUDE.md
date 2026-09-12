# 10k-financial-agent

Práctica MIAX: agente que responde preguntas sobre informes 10-K de la SEC citando de dónde sale cada dato
y eligiendo bien entre cuatro herramientas. Enunciado: `docs/00_enunciado.md`; lo que manda: `docs/01_requisitos_y_contratos.md`.
Ignora el `CLAUDE.md` de la carpeta `Downloads`: es de otro proyecto.

## Estructura

- `src/agente10k/`: todo el código. Los notebooks solo llaman a funciones de aquí.
- `notebooks/NN_*.ipynb`: un paso de la práctica cada uno; se ejecutan por separado.
- `data/`: corpus e índice FAISS. Solo lectura; se versiona byte a byte (`.gitattributes`).
- `golden/`: preguntas del golden set en JSONL.
- `resultados/<etiqueta>/`: salidas de cada ejecución (`baseline`, `final`, `ciegas`) y la escalera de recall@k
  (`retrieval`). Se versionan.
- `docs/`: guías (skills 07–13), teoría (03–06), pistas de clase (14) y el índice `docs/README.md`.

## Qué va en cada módulo

| Módulo | Qué | Guía |
| --- | --- | --- |
| `config.py` | Rutas desde la raíz, modelo fijo, clave | `docs/08` §2 |
| `datos.py` | Carga y verificación del corpus | `docs/02` |
| `herramientas.py` | Las 4 herramientas | `docs/07` |
| `retrieval.py` | Búsqueda densa, BM25, RRF, reescritura | `docs/11` |
| `agente.py` | `RespuestaFinanciera`, prompt, agente, `responder()` | `docs/08` |
| `guardrails.py` | Límite de llamadas y verificación XBRL | `docs/09` |
| `evaluacion.py` | Golden set, evaluadores, `evaluar()`, tablas | `docs/10`, `docs/12`, `docs/13` |

Los docs 07–13 sugieren más módulos (`api.py`, `evaluadores.py`, `informe.py`…): aquí están agrupados en estos siete.
También usan nombres más largos para los resultados (`baseline_golden`, `final_golden`, etiqueta `baseline-v1`). En el repo
son `resultados/baseline`, `resultados/final` y `resultados/ciegas`, con la etiqueta git `baseline`; el golden va en
`golden/golden_propio.jsonl` y los huecos, en `golden/golden_huecos.jsonl`.

## Reglas

1. **Contratos intocables** (`docs/01` §3): nombres y parámetros de `list_available`, `get_xbrl_fact`, `search_filings`
   y `read_section`; los 8 campos de `RespuestaFinanciera`; el esquema del golden; `responder(pregunta)` y
   `evaluar(ruta_jsonl)`. Solo se añaden parámetros con valor por defecto. `pytest` comprueba firmas y campos; el
   golden, `evaluacion.validar_golden()`.
2. Lógica en `src/` y notebooks finos: nada de definir en un notebook funciones que use otro.
3. Rutas siempre desde `agente10k.config`; nunca relativas al directorio actual ni absolutas.
4. Modelo fijo y `temperature=0` en todo lo evaluado; a `create_agent` se le pasa la instancia de `config.crear_modelo()`.
5. Claves solo en `.env` (no se versiona). Nunca en código ni en las salidas de los notebooks.
6. `data/` no se modifica. Los resultados del baseline no se sobrescriben: se congelan con la etiqueta git `baseline`.
7. Git: se trabaja en `main`; `git pull` antes de empezar y antes de `push`; cada uno en sus ficheros; mensajes
   en español del tipo `feat(05): bm25 + rrf` o `fix(herramientas): huecos de get_xbrl_fact`.
