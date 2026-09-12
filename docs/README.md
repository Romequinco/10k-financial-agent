# Documentación de la práctica: agente investigador sobre informes 10-K

> Requisitos: índice de R01–R15 · Empieza por: [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md) · Términos:
> [18_glosario.md](18_glosario.md)

> Fuentes: cabeceras y secciones de todos los docs de esta carpeta; `.gitignore` del repo; listado de `docs/raw/` y `data/`; mapa de
> cobertura (`docs/raw/_notas/_mapa_cobertura.md`, nota interna: §0 verificaciones V1–V7, §2 contradicciones Cxx, §4 decisiones D00–D25).

**v1.1 · 12-sep-2026.** Índice, ruta de lectura, matriz de requisitos y convenciones comunes. Las decisiones transversales (Dxx), que los docs
citan "del mapa de cobertura", están resumidas aquí para que se puedan consultar sin la nota interna. La v1.1 es la revisión de cierre:
matriz comprobada contra las secciones de cada doc, pendientes reunidos al final y enlaces, secciones citadas y claves revisados por script.

## Qué es esta carpeta

`docs/` es la documentación de trabajo del grupo para la práctica "LLMs aplicados a Finanzas" del máster MIAX: construir y evaluar un agente
que responde preguntas sobre los 10-K de seis tecnológicas (FY2024 y FY2025), eligiendo entre la consulta exacta a XBRL, la búsqueda difusa
en el texto y la lectura de una sección entera, y citando de dónde sale cada dato [enunciado · §1]. Hay cuatro tipos de documento: la
**referencia** (00–02: enunciado, requisitos y contratos, datos), la **teoría** (03–06: conceptos y "qué implica para la práctica"), las
**skills** (07–13: guías paso a paso con código mínimo y un checklist de "hecho" ligado a los `Rxx`) y el **material consolidado** por
fuente (14–17: la clase y tres repos de referencia, con sus patrones traducidos al stack fijado). Todo está escrito antes de que exista
el código, así que los nombres de módulos y ficheros (`agente10k/…`, `golden/…`, `resultados/…`) son **SUGERENCIA** hasta que se decida
la estructura del repo.

## Qué se versiona y qué no

- **Se versiona:** estos docs, el enunciado original y **`data/`**, el corpus de la práctica, para que cualquiera pueda ejecutar
  el agente en un clon limpio. `.gitattributes` guarda `data/` byte a byte, sin convertir LF a CRLF en Windows: el hash de
  `chunks.jsonl` y los offsets de carácter dependen de ello ([data/README.md](../data/README.md)). Solo se excluye
  `data/dataset.rar`, que duplica `data/dataset/`.
- **No se versiona `docs/raw/`**: material de clase, transcripciones, repos de terceros y notas de trabajo. Los docs lo citan
  para que cada afirmación se pueda rastrear, pero para comprobar una de esas citas hace falta una copia local del material.

| Carpeta | Qué contiene | De dónde sale | Cómo se cita |
| --- | --- | --- | --- |
| `docs/raw/clase/sesion1/` | Notebook `S1_Herramientas_y_Bucle_Alumno.ipynb`, `miax_s1.py` (índice y `buscar()`), `golden_set_ejemplo.jsonl`, `demo_traza.json` y una copia del enunciado `.docx` | Material de la sesión 1 de la práctica (10-sep) | `[notebook S1 · celda N]` (desde 0), `[miax_s1 · l. N]` |
| `docs/raw/clase/slides/` | PDF del módulo NLP: agenda, S1 (tokenización y embeddings), S2 (preentrenamiento), RAG y Tuning | Módulo NLP del máster | `[slides RAG · p.N]` |
| `docs/raw/clase/transcripciones/` | Transcripciones (ASR) de las clases del 4, 5 y 10 de septiembre | Clases del máster | `[transcripcion_10sep · hh:mm]` |
| `docs/raw/repos/` | Copias, en carpeta y ZIP, de `genai-labs` y `transformers-labs` (repos del profesor del módulo NLP) y de `generative-ai` (Google Cloud) | GitHub; URL en la cabecera de [15](15_repo_genai_labs.md), [16](16_repo_transformers_labs.md) y [17](17_repo_generative_ai.md) | `[genai-labs · ruta · celda N]` o `· l. N` |
| `docs/raw/_texto/` | Conversión a Markdown de notebooks, slides y transcripciones; `api_stack_langchain.md` (API real de langchain, langgraph y rank-bm25 instalados); `perfil_dataset.md` (LEEME y MANIFEST literales y perfil del corpus); `INVENTARIO.json` | Generado por el grupo a partir de lo anterior y del venv con el stack fijado | `[api_stack · sección]`, `[perfil_dataset · fichero]` |
| `docs/raw/_notas/` | Notas intermedias por fuente (clase: A1, A2, A34, A5, A6; genai-labs: B1, B2; transformers-labs: C1, C2; generative-ai: D3, D4, D12) y `_mapa_cobertura.md` | Trabajo del grupo, ya consolidado en 14–17 y en este índice | "nota A5", "D09 del mapa de cobertura" |
| `data/corpus/` **(versionado)** | `secciones.jsonl` (48 secciones), `chunks.jsonl` (1.749), `xbrl_facts.parquet` (135 hechos), `indice/` (`corpus.faiss`, `chunks_meta.parquet`, `MANIFEST.md`), `LEEME.md`, `MANIFEST.md` | Descomprimido de los ZIP del curso | Descrito en [02 §3](02_datos_corpus_y_xbrl.md) |
| `data/dataset/` **(versionado)** | `corpus_miax_2026.zip`, `indice_faiss.zip`, `fuentes_10k_html.zip` (los 12 HTML de EDGAR), `SHA256SUMS.txt` y `celda_descarga.py` (la celda 5 del notebook). No se versiona `data/dataset.rar`, que tiene el mismo contenido | Lo reparte el curso (Drive, aula virtual); no se descarga nada de EDGAR [enunciado · §3] | [02 §8](02_datos_corpus_y_xbrl.md) |

El corpus va en el repo, listo en `data/corpus/`. Queda decidido que la ruta sea configurable, con un valor por defecto relativo a
la raíz del repo, y que un SHA-256 que no cuadre pare la ejecución (D25, [02 §8](02_datos_corpus_y_xbrl.md)). El enunciado original,
[Practica_LLM_Agente_10K.docx](Practica_LLM_Agente_10K.docx), también está en `docs/` y se versiona.

## Ruta rápida para el 17 de septiembre

El jueves 17 hay que llegar con **el baseline corriendo en el repo, con `responder()` y `evaluar()`,** y **20 preguntas propias que pasen
`validar()`, con al menos 6 comparativas** [notebook S1 · celda 33]. La sesión empieza ejecutando cada baseline contra cinco preguntas duras,
y sin agente "la primera hora se convierte en soporte técnico" [14 §1](14_clase_pistas_del_profesor.md). Orden de lectura:

| # | Qué leer | Para qué | Reparto (sugerencia) |
| --- | --- | --- | --- |
| 1 | [01](01_requisitos_y_contratos.md) entero; [00](00_enunciado.md) §3–§5 y §7 | Contratos que no se tocan, R01–R15, trampas de los datos y fallos del notebook | Los tres |
| 2 | [14](14_clase_pistas_del_profesor.md) §1–§3 y §5 | Qué pidió el profesor, sus avisos y qué TODO y asserts del notebook S1 no prueban nada | Los tres |
| 3 | [02](02_datos_corpus_y_xbrl.md) §1–§7 | El "paseíto por el dataset": items, cierres fiscales, cobertura XBRL, huecos y carga | Los tres |
| 4a | [08](08_skill_agente_salida_estructurada.md) §1–§2, §6–§7 y §10; [07](07_skill_herramientas_docstrings.md) §4; [12](12_skill_evaluadores.md) §2 y §8 | Baseline (D21): tools y `SYSTEM` del notebook, modelo como instancia a `temperature=0`, arnés `ejecutar()`/`responder()`, `evaluar()` que guarda `predicciones.jsonl` y prueba de humo con la API real | Una persona |
| 4b | [10](10_skill_golden_set.md) entero, con [02](02_datos_corpus_y_xbrl.md) §5 y §9 | Golden: reparto, comparativas, anclas, `validar()` y `validar_estricto()`, y el fichero aparte de huecos | Los tres, ~7 preguntas cada uno [10 §1](10_skill_golden_set.md) |
| 5 | [13](13_skill_medicion_informe_presentacion.md) §3 | Commit del golden **antes** de ejecutar, ejecución del baseline y etiqueta `baseline-v1` | Una persona |
| 6 | Si sobra tiempo: [05](05_teoria_agentes_react_tools.md) §2–§4 | Qué ve el modelo, el bucle ReAct y `create_agent` | — |

Checklist del 17:

- [ ] Baseline (D21) en el repo: `responder()` devuelve siempre un `RespuestaFinanciera` y `evaluar()` corre sobre dos preguntas.
- [ ] Prueba de humo con la API real hecha y dudas anotadas para la sesión ([08 §10](08_skill_agente_salida_estructurada.md)), junto a
      las preguntas P1–P15 de [Pendientes y dudas abiertas](#pendientes-y-dudas-abiertas).
- [ ] Golden propio: 20 preguntas, ≥ 6 comparativas, `validar(..., exigir_20=True)` y `validar_estricto()` en verde, revisado en pareja y con
      commit ([10 §8–§9](10_skill_golden_set.md)).
- [ ] 3–5 huecos en un fichero aparte, fuera de los 20 (D11, [10 §5](10_skill_golden_set.md)).
- [ ] Recomendado: los tres TODO del notebook comprobados ejecutando la trayectoria y no solo con los asserts
      ([14 §5](14_clase_pistas_del_profesor.md)), y el baseline ejecutado sobre el golden y congelado con `baseline-v1`.
- [ ] Ninguna clave en el repo (R13).

**Después del 17**, en el orden de la sesión 2: [09](09_skill_guardrails_middleware_xbrl.md) (límites y R05) → [03](03_teoria_tokenizacion_embeddings.md)
y [04](04_teoria_rag_retrieval.md) → [11](11_skill_mejora_retrieval.md) (escalera de retrieval) → [07](07_skill_herramientas_docstrings.md) §5–§9
(tools finales) → [06](06_teoria_evaluacion_llms.md) → [12](12_skill_evaluadores.md) → [13](13_skill_medicion_informe_presentacion.md).

## Mapa de documentos

| Doc | Qué contiene | Requisitos |
| --- | --- | --- |
| **Referencia** | | |
| [00_enunciado.md](00_enunciado.md) | Conversión fiel del enunciado: objetivo, contexto, datos, tareas, entregables, criterios y anexo de código con los contratos | Origen de todos |
| [Practica_LLM_Agente_10K.docx](Practica_LLM_Agente_10K.docx) | Enunciado original (manda sobre la conversión) | — |
| [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md) | Calendario, R01–R15 con su criterio de "hecho", contratos (tools, `RespuestaFinanciera`, golden), stack fijado, trampas de los datos, fallos del notebook S1 y puntos abiertos | Define R01–R15 |
| [02_datos_corpus_y_xbrl.md](02_datos_corpus_y_xbrl.md) | El 10-K y sus cuatro items, cierres fiscales, ficheros del corpus, tokens por sección, cobertura y valores XBRL, trampas, carga, clon limpio y qué preguntas permiten los datos | R01, R06, R07, R14 (y R05, R08, R10) |
| **Teoría** | | |
| [03_teoria_tokenizacion_embeddings.md](03_teoria_tokenizacion_embeddings.md) | Tokens y tokenizers, de la bolsa de palabras a BM25, embeddings (bi-encoder, bge-small), búsqueda exacta frente a ANN | R08, R11 (y R02, R05, R07, R09b) |
| [04_teoria_rag_retrieval.md](04_teoria_rag_retrieval.md) | RAG clásico frente a retrieval como herramienta, chunking, denso, disperso e híbrido (RRF), pre y post-filtro, transformar la consulta, reranking, evaluar el retrieval, tablas y números | R08, R09 (y R07, R11, R14) |
| [05_teoria_agentes_react_tools.md](05_teoria_agentes_react_tools.md) | Tool calling (qué ve el modelo y quién ejecuta), ReAct, `create_agent`, salida estructurada (Provider, Tool y Auto), middleware y hooks, patrones, API obsoleta, MCP, A2A y ADK | R01–R05 (y R11, R14, R15) |
| [06_teoria_evaluacion_llms.md](06_teoria_evaluacion_llms.md) | Qué se evalúa y contra qué, métricas de texto y por qué no bastan, P/R/F1, métricas de retrieval, trayectoria, LLM-as-a-judge, tolerancias, abstención, muestras pequeñas, hold-out, coste y latencia | R09, R11, R15 (y R08, R12, R14) |
| **Skills** | | |
| [07_skill_herramientas_docstrings.md](07_skill_herramientas_docstrings.md) | Las cuatro tools: reglas de diseño, plantilla del docstring, baseline, código final, experimento docstring vago frente a preciso, tests y medida del enrutado | R01, R02, R14 (alimenta R04, R05, R08, R09c, R15) |
| [08_skill_agente_salida_estructurada.md](08_skill_agente_salida_estructurada.md) | Clave y modelo, esquema `RespuestaFinanciera` y sus añadidos, `ToolStrategy`, system prompt, montaje, `ejecutar()` y `responder()`, depuración, prueba de humo con la API real y tests | R03, R04 (montaje), R10, R13 |
| [09_skill_guardrails_middleware_xbrl.md](09_skill_guardrails_middleware_xbrl.md) | Pila de límites, bucles repetidos, extraer y comparar cifras (`parse_cifras`, `cifra_ok`), `VerificadorXBRL`, casos no verificables, tests, entradas fuera del corpus y cómo contarlo | R04, R05, R14 |
| [10_skill_golden_set.md](10_skill_golden_set.md) | Proceso, esquema campo a campo, reparto, comparativas, huecos, cómo encontrar anclas, plantillas, `validar_estricto()` y generación asistida | R06, R07, R14 (alimenta R08, R09, R11) |
| [11_skill_mejora_retrieval.md](11_skill_mejora_retrieval.md) | Protocolo "un cambio cada vez", recall@k contra el ancla, filtro por metadatos, BM25 + RRF, reescritura, escalera, integración en `search_filings` sin tocar la firma y diagnósticos | R08, R11 (recall@k), R12 |
| [12_skill_evaluadores.md](12_skill_evaluadores.md) | Evaluadores (a) cita, (b) cifra, (c) trayectoria y (d) abstención, `correcta` y acierto por familia; jueces con caché y su validación; `evaluar()` y `puntuar()`; tests; las ciegas sin tocar código | R09, R10, R11, R12 (y R14, R15) |
| [13_skill_medicion_informe_presentacion.md](13_skill_medicion_informe_presentacion.md) | Coste, latencia y llamadas; congelar el baseline; ejecución final; tabla R11 y secundarias generadas por código; registro de experimentos; protocolo del 24; PDF y presentación; checklist de entrega | R11, R12, R13, R15 (y R10, R14) |
| **Material consolidado** | | |
| [14_clase_pistas_del_profesor.md](14_clase_pistas_del_profesor.md) | Lo que dijo la clase y no está (o no está claro) en el enunciado: sesión 1, aclaraciones, avisos, preguntas, TODO y fallos del notebook S1, próximas sesiones, ideas de las clases teóricas y dudas para el profesor | Todos, vía `Rxx` |
| [15_repo_genai_labs.md](15_repo_genai_labs.md) | genai-labs: del `max_steps` al middleware, detección de bucles, bucle a mano, verificador XBRL, juez de tres etiquetas, `responder()`, reescritura, prompt y claves; snippets ejecutados con modelo falso | R02–R05, R08, R09a, R10, R11, R13, R14 |
| [16_repo_transformers_labs.md](16_repo_transformers_labs.md) | transformers-labs: recall@k y MRR contra el ancla, cita literal, tolerancia de cifras, trayectoria como conjuntos, FAISS exacto + BM25, coste, latencia y tabla micro/macro, conteo de tokens | R05, R07–R09, R11, R12 (y R10, R13–R15) |
| [17_repo_generative_ai.md](17_repo_generative_ai.md) | generative-ai: trayectoria y enrutado, juez frase a frase y su validación, errores como datos, salida estructurada condicional, límites con tests, coste por llamada, RRF, golden asistido y abstención estilo hallcheck | R01–R09, R11, R12, R14, R15 |
| **Índice** | | |
| [README.md](README.md) | Este documento | — |
| [18_glosario.md](18_glosario.md) | Términos en una o dos líneas, con enlace al doc donde se tratan | — |

## Matriz R01–R15 → docs

Primero la skill (el "cómo"); la teoría da el porqué y 14–17 los patrones de origen. Enunciado y criterio de "hecho" de cada requisito:
[01 §2](01_requisitos_y_contratos.md).

| R | Requisito | Skill | Teoría | Datos y contratos | Apoyo (14–17) |
| --- | --- | --- | --- | --- | --- |
| R01 | Cuatro tools con las firmas del contrato | [07](07_skill_herramientas_docstrings.md) §1, §5, §8 | [05](05_teoria_agentes_react_tools.md) §2 | [01](01_requisitos_y_contratos.md) §3; [02](02_datos_corpus_y_xbrl.md) §1–§6 | [14](14_clase_pistas_del_profesor.md) §5; [17](17_repo_generative_ai.md) §3.3 |
| R02 | Docstrings de enrutado | [07](07_skill_herramientas_docstrings.md) §2–§3, §7; [08](08_skill_agente_salida_estructurada.md) §5 | [05](05_teoria_agentes_react_tools.md) §2 | [02](02_datos_corpus_y_xbrl.md) §5–§6 (vocabulario) | [15](15_repo_genai_labs.md) §3.8; [17](17_repo_generative_ai.md) §3.3 |
| R03 | Salida estructurada `RespuestaFinanciera` | [08](08_skill_agente_salida_estructurada.md) §3–§4 | [05](05_teoria_agentes_react_tools.md) §5 | [01](01_requisitos_y_contratos.md) §3 | [15](15_repo_genai_labs.md) §3.8; [17](17_repo_generative_ai.md) §3.4 |
| R04 | Límite de llamadas por invocación | [09](09_skill_guardrails_middleware_xbrl.md) §2–§3; [08](08_skill_agente_salida_estructurada.md) §6–§7 | [05](05_teoria_agentes_react_tools.md) §4, §6 | [01](01_requisitos_y_contratos.md) §4 | [14](14_clase_pistas_del_profesor.md) §5; [15](15_repo_genai_labs.md) §3.1–§3.3; [17](17_repo_generative_ai.md) §3.5 |
| R05 | Middleware de verificación contra XBRL | [09](09_skill_guardrails_middleware_xbrl.md) §4–§7 | [05](05_teoria_agentes_react_tools.md) §6; [06](06_teoria_evaluacion_llms.md) §7 | [02](02_datos_corpus_y_xbrl.md) §5 | [15](15_repo_genai_labs.md) §3.4; [16](16_repo_transformers_labs.md) §3.3; [17](17_repo_generative_ai.md) §3.5 |
| R06 | Golden set propio (20, ≥ 6 comparativas) | [10](10_skill_golden_set.md) | [06](06_teoria_evaluacion_llms.md) §10 | [01](01_requisitos_y_contratos.md) §3, §6; [02](02_datos_corpus_y_xbrl.md) §9 | [14](14_clase_pistas_del_profesor.md) §5; [17](17_repo_generative_ai.md) §3.8 |
| R07 | Anclas de texto, no `chunk_id` | [10](10_skill_golden_set.md) §2, §6; [11](11_skill_mejora_retrieval.md) §2, §4 | [04](04_teoria_rag_retrieval.md) §2; [06](06_teoria_evaluacion_llms.md) §4 | [02](02_datos_corpus_y_xbrl.md) §3 | [16](16_repo_transformers_labs.md) §3.1–§3.2 |
| R08 | Mejora medida del retrieval | [11](11_skill_mejora_retrieval.md) | [03](03_teoria_tokenizacion_embeddings.md); [04](04_teoria_rag_retrieval.md) | [02](02_datos_corpus_y_xbrl.md) §3 | [15](15_repo_genai_labs.md) §3.7; [16](16_repo_transformers_labs.md) §3.1, §3.5; [17](17_repo_generative_ai.md) §3.7 |
| R09 | Tres evaluadores | [12](12_skill_evaluadores.md) §3–§6, §9 | [06](06_teoria_evaluacion_llms.md) §5–§7; [04](04_teoria_rag_retrieval.md) §7 | [02](02_datos_corpus_y_xbrl.md) §5 | [15](15_repo_genai_labs.md) §3.5; [16](16_repo_transformers_labs.md) §3.2–§3.4; [17](17_repo_generative_ai.md) §3.1–§3.2 |
| R10 | `responder()` y `evaluar()` en un clon limpio | [08](08_skill_agente_salida_estructurada.md) §7; [12](12_skill_evaluadores.md) §8, §11; [13](13_skill_medicion_informe_presentacion.md) §10 | — | [02](02_datos_corpus_y_xbrl.md) §8 | [15](15_repo_genai_labs.md) §3.6; [16](16_repo_transformers_labs.md) §3.6 |
| R11 | Tabla baseline frente a final | [13](13_skill_medicion_informe_presentacion.md) §2, §5; [11](11_skill_mejora_retrieval.md) §10; [12](12_skill_evaluadores.md) §7 | [06](06_teoria_evaluacion_llms.md) §3, §11; [03](03_teoria_tokenizacion_embeddings.md) §1 | [01](01_requisitos_y_contratos.md) §4 (precios) | [15](15_repo_genai_labs.md) §3.6; [16](16_repo_transformers_labs.md) §3.6; [17](17_repo_generative_ai.md) §3.6 |
| R12 | Resultados regenerables, baseline congelado | [13](13_skill_medicion_informe_presentacion.md) §3–§5; [12](12_skill_evaluadores.md) §8; [11](11_skill_mejora_retrieval.md) §8 | [06](06_teoria_evaluacion_llms.md) §9–§10 | — | [16](16_repo_transformers_labs.md) §3.6; [17](17_repo_generative_ai.md) §3.8 |
| R13 | Sin claves en el repo | [08](08_skill_agente_salida_estructurada.md) §2; [13](13_skill_medicion_informe_presentacion.md) §10 | — | — | [15](15_repo_genai_labs.md) §3.9; [16](16_repo_transformers_labs.md) §4 |
| R14 | Honestidad ante huecos | [09](09_skill_guardrails_middleware_xbrl.md) §6, §8; [10](10_skill_golden_set.md) §5; [12](12_skill_evaluadores.md) §7; [07](07_skill_herramientas_docstrings.md) §5; [13](13_skill_medicion_informe_presentacion.md) §6 (tabla de abstención) | [06](06_teoria_evaluacion_llms.md) §8 | [02](02_datos_corpus_y_xbrl.md) §6, §9 | [15](15_repo_genai_labs.md) §3.2; [17](17_repo_generative_ai.md) §3.9 |
| R15 | Presentación e informe | [13](13_skill_medicion_informe_presentacion.md) §6–§9; [07](07_skill_herramientas_docstrings.md) §9; [09](09_skill_guardrails_middleware_xbrl.md) §10 | [06](06_teoria_evaluacion_llms.md) §9–§10 | — | [14](14_clase_pistas_del_profesor.md) §2–§3; [17](17_repo_generative_ai.md) §3.1, §3.9 |

## Convenciones

### Estructura de cada doc

- Cabecera `> Requisitos: … · Lee antes: … · Después: …`, bloque `> Fuentes: …` y línea `**vX · fecha.**` con las marcas que usa.
- **Teoría (03–06):** conceptos y una sección "Qué implica para la práctica", sin recetas largas.
- **Skills (07–13):** pasos con código mínimo, "Trampas" y un "Checklist de hecho" ligado a los `Rxx`; enlazan a la teoría y a 14–17 en
  lugar de repetirlos.
- **Consolidados:** 14 sigue el orden de la clase; 15–17, el de cada repo: mapa de utilidad, patrones "traducidos a nuestro stack", APIs
  obsoletas con su equivalente, qué no aplica y orden de lectura.
- El vocabulario común (acierto, hueco, ancla, escalera, techo, modo aislado…) está en [18_glosario.md](18_glosario.md).

### Formato de las citas

| Cita | Remite a |
| --- | --- |
| `[enunciado · §N]` | [00_enunciado.md](00_enunciado.md), sección N |
| `[01 §N]`, `[14 §5]`, `[11 §6]` | Doc hermano, sección N (en el texto, con enlace relativo) |
| `[notebook S1 · celda N]` | Notebook de la sesión 1; celdas contadas **desde 0** |
| `[miax_s1 · l. N]` o `miax_s1.py · buscar()` | Módulo auxiliar de la sesión 1 |
| `[transcripcion_10sep · hh:mm]` | Marca de tiempo de la transcripción (ASR corregido por contexto) |
| `[slides RAG · p.N]`, `diap. N` | Página del PDF; `diap.` = número impreso en la diapositiva |
| `[genai-labs · ruta · celda N]`, `[generative-ai · ruta · l. N]` | Fichero de un repo de terceros (celdas desde 0); abreviaturas de rutas en la cabecera de cada doc |
| `[api_stack · sección]` | `docs/raw/_texto/api_stack_langchain.md`: API real del stack instalado |
| `[perfil_dataset · fichero]` | `docs/raw/_texto/perfil_dataset.md`: LEEME, MANIFEST y perfil del corpus |
| "nota A5", "D09 del mapa de cobertura" | Nota intermedia de `docs/raw/_notas/`; Dxx, Cxx y Vx se resumen abajo |

### Marcas de verificación

| Marca | Significa |
| --- | --- |
| **(probado)** | Ejecutado en un venv con el stack fijado y un modelo falso (`GenericFakeChatModel`), sin red. Confirma la API y el flujo, **no** cómo se comporta Gemini |
| **(venv)** | Comprobado por introspección del código instalado (imports, firmas, valores por defecto) |
| **(datos)** | Calculado sobre `data/corpus/` (solo lectura) |
| **(compila)** | Solo `py_compile`: el venv del stack no tiene faiss, sentence-transformers ni pandas |
| **(cálculo propio)** | Aritmética hecha para el doc, sin fuente externa |
| ⚠️ | Sin verificar, o **por verificar**: pendiente de probar con el modelo real, de contrastar con la fuente o de preguntar al profesor. Quien lo verifique quita el ⚠️ y deja la marca y la fuente |
| **Revisar tras el 17-sep / 18-sep / 19-sep** | Doc que depende de una sesión que aún no ha ocurrido (hoy: 04, 05, 07, 11 y 12) |
| **SUGERENCIA** | Nombres de módulos, ficheros y variables de entorno propuestos; las reglas que acompañan no son sugerencia |

**Jerarquía cuando dos fuentes chocan:** manda el enunciado; después, lo verificado en el stack o en los datos; después, la clase; por
último, los repos. Los contratos de [01 §3](01_requisitos_y_contratos.md) no se cambian en ningún caso.

### Decisiones transversales (D00–D25)

Son de obligado cumplimiento para todos los docs. Para apartarse de una, primero se cambia la decisión (aquí y en el mapa de cobertura) y
después los docs que la citan.

| D | Decisión | Dónde |
| --- | --- | --- |
| D00 | Convenciones de redacción: las de esta sección | Este README |
| D01 | Modelo `openrouter:google/gemini-3.8-flash` con `init_chat_model(…, temperature=0)`; a `create_agent` se le pasa **la instancia**, nunca la cadena. Nada de `openrouter:auto` ni de *fallback* de modelo en ejecuciones evaluadas. Juez: el mismo modelo a `temperature=0`, configurable aparte | [08 §2](08_skill_agente_salida_estructurada.md) |
| D02 | `response_format=ToolStrategy(schema=RespuestaFinanciera)` explícito (con este modelo, el esquema suelto ya acaba en `ToolStrategy`, V1). `structured_response` puede ser `None`: siempre hay *fallback*. Juez y reescritor, con `create_agent(tools=[])`; nunca `with_structured_output` | [08 §4](08_skill_agente_salida_estructurada.md), [05 §5](05_teoria_agentes_react_tools.md) |
| D03 | Los 8 campos del contrato más `concept_xbrl`, `ejercicio_base` y `cifra_base`, opcionales. `cifra` sin escalar, en la unidad de XBRL; `cita` literal de un fragmento leído. `model_validator` con tres reglas, solo en el final | [08 §3](08_skill_agente_salida_estructurada.md) |
| D04 | Final: `ToolCallLimitMiddleware(run_limit=8)` + `ToolCallLimitMiddleware(tool_name="read_section", run_limit=2)` + `ModelCallLimitMiddleware(run_limit=12, exit_behavior="end")` + `VerificadorXBRL` (argumentos solo por nombre, venv). Arnés igual en baseline y final: `recursion_limit=100` y excepciones capturadas. *Fallback* único con `fuente="ninguna"` | [09 §2](09_skill_guardrails_middleware_xbrl.md), [08 §7](08_skill_agente_salida_estructurada.md) |
| D05 | Un `thread_id` nuevo por pregunta, nunca reutilizado | [08 §7](08_skill_agente_salida_estructurada.md) |
| D06 | Una sola `cifra_ok()` para R05 y el evaluador (b): USD con tolerancia relativa del 0,5 %, BPA absoluta de 0,005, hueco si `cifra is None`; los % derivados, solo diagnóstico | [09 §4](09_skill_guardrails_middleware_xbrl.md), [12 §3](12_skill_evaluadores.md), [06 §7](06_teoria_evaluacion_llms.md) |
| D07 | Una sola `normalizar()` (NFKC, comillas y guiones a ASCII, minúsculas, espacios colapsados) para anclas, citas y recall; las cifras se comparan como números | [09 §4](09_skill_guardrails_middleware_xbrl.md), [16 §3.2](16_repo_transformers_labs.md) |
| D08 | recall@k = algún chunk del top-k contiene el ancla normalizada. Principal @5; @1, @3, @10 y MRR@10 salen de un único top-20. Modo aislado (tabla) y dentro del agente (diagnóstico); antes, `anclas_no_indexables` = 0 | [11 §2, §4](11_skill_mejora_retrieval.md), [06 §4](06_teoria_evaluacion_llms.md) |
| D09 | Escalera: 0 denso → 1 + filtro oráculo → 2 + BM25 con RRF (k=60, pesos iguales, `n_cand=20`) → 3 + reescritura con los filtros del LLM. Hiperparámetros fijados antes de medir; la `search_filings` final envuelve la misma función sin cambiar la firma | [11 §2–§9](11_skill_mejora_retrieval.md), [04](04_teoria_rag_retrieval.md) |
| D10 | Comparativas: `fiscal_year` = FY reciente y `cifra_esperada` = su nivel XBRL; ancla del FY reciente; extras `fiscal_year_base`, `cifra_esperada_base`; `herramienta_esperada = ["get_xbrl_fact", "search_filings"]` | [10 §4](10_skill_golden_set.md) |
| D11 | Los huecos van fuera de los 20, en un fichero aparte con `hueco: true`. Acierto = `fuente="ninguna"` ∧ `cifra is None` ∧ (c). Se mide también la abstención indebida | [10 §5](10_skill_golden_set.md), [12 §7](12_skill_evaluadores.md) |
| D12 | (c) trayectoria: todas las herramientas esperadas (AND, sin orden; `list_available` neutra), sobre los `tool_calls` filtrados por lista blanca y sin deduplicar, más los argumentos de `get_xbrl_fact`. `herramienta_esperada` (contrato) lleva **solo nombres reales**; las alternativas, en el extra `herramienta_alternativa` (p. ej. `{"search_filings": ["read_section"]}`) | [12 §4](12_skill_evaluadores.md), [06 §5](06_teoria_evaluacion_llms.md) |
| D13 | (a) cita: etapa 1 determinista (`existe` en la sección ∧ `vista` en un `ToolMessage`) y etapa 2, juez frase a frase; el juez se valida con 30–40 pares a mano y kappa | [12 §5–§6, §9](12_skill_evaluadores.md), [06 §6](06_teoria_evaluacion_llms.md) |
| D14 | Acierto: numérica (b)∧(c); extractiva (a)∧(c)∧`correcta`; comparativa (a)∧(b)∧(c)∧`correcta`; hueco, D11. Micro y macro, siempre con k/n | [12 §7](12_skill_evaluadores.md) |
| D15 | R05: `after_model` que contrasta `cifra`, `cifra_base` y los importes de la prosa con los valores del parquet de las `get_xbrl_fact` llamadas; un reintento con el desajuste y, si vuelve a fallar, abstención | [09 §5–§6](09_skill_guardrails_middleware_xbrl.md) |
| D16 | Coste: `get_usage_metadata_callback` por pregunta × precios fechados, contrastado con `usage_metadata`; el juez va aparte | [13 §2](13_skill_medicion_informe_presentacion.md) |
| D17 | Latencia: `perf_counter` alrededor de `invoke`, tras calentar, en secuencia; media y mediana | [13 §2](13_skill_medicion_informe_presentacion.md) |
| D18 | Llamadas por pregunta: `tool_calls` de la lista blanca, contando repetidas y bloqueadas | [13 §2](13_skill_medicion_informe_presentacion.md) |
| D19 | Resultados en `resultados/<etiqueta>/` (`predicciones.jsonl`, `puntuaciones.jsonl`, `resumen.json`); etiquetas git `baseline-v1` y `final-v1`; ejecutar ≠ puntuar | [12 §8](12_skill_evaluadores.md), [13 §3–§5](13_skill_medicion_informe_presentacion.md) |
| D20 | `responder()` siempre devuelve un `RespuestaFinanciera` válido; `evaluar()` aísla cada pregunta con `try/except`, lee los campos con `.get` y no exige que el fichero pase `validar()` | [08 §7](08_skill_agente_salida_estructurada.md), [12 §8, §11](12_skill_evaluadores.md) |
| D21 | Baseline = la versión del profesor (tools, docstrings, `SYSTEM` y `create_agent` del notebook, sin middleware) con solo dos cambios: modelo como instancia a `temperature=0` y el arnés. Todo lo demás es mejora medida | [08 §1](08_skill_agente_salida_estructurada.md), [07 §4](07_skill_herramientas_docstrings.md), [13 §3](13_skill_medicion_informe_presentacion.md) |
| D22 | Tools finales: firmas del contrato, devuelven `str`, normalizan entradas y nunca lanzan; BPA con dos decimales y "no reportó…" sin estimar; `list_available` sin la lista de huecos; ninguna tool llama a otra del contrato | [07 §2, §5](07_skill_herramientas_docstrings.md) |
| D23 | Módulos sugeridos (SUGERENCIA): `agente10k/` con `config`, `datos`, `normalizacion`, `retrieval`, `herramientas`, `esquemas`, `middleware`, `agente`, `api`, `evaluadores`, `metricas_retrieval` e `informe`; `golden/`; `tests/` | Bloques de código de 07–13 |
| D24 | Precios de [01 §4](01_requisitos_y_contratos.md) (2-sep), revisados el 22-sep y guardados con la fecha junto a los resultados | [13 §2](13_skill_medicion_informe_presentacion.md) |
| D25 | Clon limpio: pines de la celda 2 + `pandas` y `pyarrow`; ruta del corpus configurable y SHA-256 que para si no cuadra; `OPENROUTER_API_KEY` por entorno o `getpass`; ensayo antes del 22-sep | [13 §10](13_skill_medicion_informe_presentacion.md), [02 §8](02_datos_corpus_y_xbrl.md) |

### Contradicciones resueltas (Cxx) y verificaciones (Vx) citadas en los docs

| C | Tema | Resolución | Dónde |
| --- | --- | --- | --- |
| C01 | Fecha de entrega: "el 24" en clase, 23-sep 23:59 en el enunciado | 23-sep | [01 §6](01_requisitos_y_contratos.md), [13 §1](13_skill_medicion_informe_presentacion.md) |
| C02 | `response_format` "opcional" en clase | Obligatorio (enunciado) | [05 §5](05_teoria_agentes_react_tools.md) |
| C03 | ¿Hace falta `ToolStrategy`? | Con nuestro modelo el esquema suelto ya lo es; se escribe explícito | [05 §5](05_teoria_agentes_react_tools.md), [08 §4](08_skill_agente_salida_estructurada.md) |
| C06 | Tolerancia del BPA | Absoluta 0,005 | [06 §7](06_teoria_evaluacion_llms.md), [12 §3](12_skill_evaluadores.md) |
| C07 | Acierto en recall@k: substring o cobertura de 4-gramas | Substring normalizado; la cobertura, solo diagnóstico | [06 §4](06_teoria_evaluacion_llms.md), [11 §4](11_skill_mejora_retrieval.md) |
| C09 | nDCG o MRR | MRR@10 | [06 §4](06_teoria_evaluacion_llms.md) |
| C10 | Formato del juez de cita | Razonamiento primero y etiqueta por frase | [06 §6](06_teoria_evaluacion_llms.md), [12 §6](12_skill_evaluadores.md) |
| C14 | `herramienta_esperada` de las comparativas | `get_xbrl_fact` + `search_filings` | [10 §4](10_skill_golden_set.md), [12 §4](12_skill_evaluadores.md) |
| C15 | `list_available` "ya no tiene sentido" | Se mantiene (contrato) | [07](07_skill_herramientas_docstrings.md) |
| C16 | ¿`list_available` lista los huecos? | No; los dice `get_xbrl_fact` | [07 §2](07_skill_herramientas_docstrings.md) |
| C17 | Detectar la "cita vista" | Firma `-> str`; se busca en el contenido de los `ToolMessage` | [07 §2](07_skill_herramientas_docstrings.md), [12 §5](12_skill_evaluadores.md) |
| C18 | Constante de RRF | k = 60, pesos iguales | [04 §3](04_teoria_rag_retrieval.md), [11 §6](11_skill_mejora_retrieval.md) |
| C19 | Tokenizer de BM25 | `[a-z0-9]+`; las variantes, como experimento | [03 §2](03_teoria_tokenizacion_embeddings.md), [11 §6](11_skill_mejora_retrieval.md) |
| C20 | Qué cuenta como "filtro por metadatos" | Filtros oráculo (techo) + % de filtros correctos del agente + pre-filtro en el híbrido | [04 §4](04_teoria_rag_retrieval.md), [11 §5](11_skill_mejora_retrieval.md) |
| C21 | Dónde vive la reescritura | La escribe el modelo en los argumentos; se mide aislada con `reescribir()` | [04 §5](04_teoria_rag_retrieval.md), [11 §7](11_skill_mejora_retrieval.md) |
| C26 | ¿Deduplicar llamadas en la trayectoria? | No | [06 §5](06_teoria_evaluacion_llms.md), [12 §4](12_skill_evaluadores.md) |
| C27 | ¿Embeddings propios? | Se mantiene bge; otro modelo es experimento opcional | [11 §11](11_skill_mejora_retrieval.md) |
| C28 | Sobre qué golden va la tabla | El propio; el oficial, si llega, como fila extra | [13 §5](13_skill_medicion_informe_presentacion.md) |
| C29 | "Run all" en Colab | Repo + `evaluar()`; notebook de demo opcional | [13 §10](13_skill_medicion_informe_presentacion.md) |

Verificaciones: **V1** `create_agent` envuelve un esquema suelto en `AutoStrategy`, que con nuestro modelo acaba en `ToolStrategy` (venv);
**V2** `recursion_limit` cuenta *supersteps*, unos 2 por llamada al modelo sin middleware y 6–7 con la pila de D04 (probado); **V3** un
`after_model` puede pedir un reintento y, si falla otra vez, sustituir la respuesta (probado); **V4** firmas de los middleware de límite y
de `ChatOpenRouter` (venv); **V5** `ancla_inicio`/`ancla_fin` son offsets de carácter `[inicio, fin)` sobre el texto de la sección (datos);
**V6** el 60 % de los pares de chunks consecutivos no se solapa (datos); **V7** `ej-003` del golden de ejemplo no sirve de modelo (datos).
Detalle en [05 §4–§6](05_teoria_agentes_react_tools.md), [02 §3](02_datos_corpus_y_xbrl.md) y [01 §6](01_requisitos_y_contratos.md).

## Pendientes y dudas abiertas

Reúne, sin repetir, las dudas de [01 §6](01_requisitos_y_contratos.md) y [14 §8](14_clase_pistas_del_profesor.md), los ⚠️ de los docs y
los huecos del mapa de cobertura (§3) que la revisión de cierre del 12-sep dejó abiertos: primero lo que hay que preguntar al profesor y
después lo que hay que verificar al implementar. Quien cierre un punto lo quita de aquí y quita el ⚠️ del doc afectado; si la respuesta
cambia una decisión provisional, se cambia antes la Dxx o la Cxx de las tablas de arriba.

### Para preguntar al profesor el 17-sep

Mientras no conteste, vale lo provisional de la tercera columna. "Duda N" es la numeración de [14 §8](14_clase_pistas_del_profesor.md).

| # | Pregunta | Mientras tanto | Dónde |
| --- | --- | --- | --- |
| P1 | ¿Se entrega el 23-sep a las 23:59 (enunciado) o el 24 (clase y notebook)? | El 23 (C01) | [01 §6](01_requisitos_y_contratos.md); duda 1 |
| P2 | ¿Hay que elegir y generar un modelo de embeddings propio o basta el índice de bge-small entregado? Si se cambia, ¿el baseline se queda con el índice original? | bge; otro modelo es un experimento opcional, con índice y manifiesto nuevos (C27) | [11 §11](11_skill_mejora_retrieval.md); duda 2 |
| P3 | ¿Cuándo llega el golden oficial (`golden_set.jsonl`, 20 preguntas)? ¿La tabla baseline/final va sobre las 20 oficiales, las propias o ambas? | Golden propio; el oficial, como fila extra (C28) | [01 §6](01_requisitos_y_contratos.md), [13 §5](13_skill_medicion_informe_presentacion.md); duda 3 |
| P4 | Comparativas: ¿cómo se representa el segundo ejercicio, si la celda 30 dice "por cada ejercicio" y el validador admite uno? ¿`cifra_esperada` es el nivel del FY reciente o la variación? | D10: FY reciente, su nivel XBRL y los extras `*_base` | [10 §4](10_skill_golden_set.md); duda 4 |
| P5 | Huecos ("no está en el corpus"): ¿cómo se codifican, si `validar()` exige cifra en las numéricas y ancla en las extractivas? | D11: fichero aparte con `hueco: true`, fuera de los 20 | [10 §5](10_skill_golden_set.md); duda 5 |
| P6 | Evaluador de trayectoria del 24: ¿exige todas las herramientas de `herramienta_esperada`, alguna o en orden? ¿Mira los argumentos? ¿Penaliza llamadas de más, como `list_available`? | D12: todas, sin orden y sin deduplicar, `list_available` neutra, más los argumentos de `get_xbrl_fact` | [12 §4](12_skill_evaluadores.md), [16 §3.4](16_repo_transformers_labs.md); duda 6 |
| P7 | ¿Los falsos "ninguna" van como cuarto evaluador o dentro de los tres? ¿Hay una tolerancia de referencia para las cifras? | Abstención (d) aparte (D11, D14); tolerancias de D06 | [12 §3, §7](12_skill_evaluadores.md); duda 7 |
| P8 | ¿Qué cuenta como "filtro por metadatos": que el LLM pase los filtros, un pre-filtro antes de cortar el top-N del híbrido o una extracción determinista? | C20: filtros oráculo (techo) + % de filtros correctos del agente + pre-filtro en el híbrido | [11 §5](11_skill_mejora_retrieval.md); duda 8 |
| P9 | Ciegas: ¿en qué formato llegan (¿JSONL con el esquema del golden?), en qué idioma y entorno, y quién lanza `evaluar()`? ¿Traen ancla para medir recall? ¿Incluyen huecos? | `evaluar()` lee los campos con `.get` y no exige `validar()` (D20); ensayo con diez ciegas simuladas | [12 §11](12_skill_evaluadores.md), [13 §8](13_skill_medicion_informe_presentacion.md); duda 9 |
| P10 | ¿Aplica a esta práctica el "Run all" de Colab de la agenda del módulo NLP? | Repo + `evaluar()`; notebook de demo opcional (C29) | [01 §6](01_requisitos_y_contratos.md), [13 §10](13_skill_medicion_informe_presentacion.md); duda 10 |
| P11 | Límite de llamadas: ¿qué `exit_behavior` espera (`"continue"`, el defecto, o `"end"`)? ¿Cuentan todas las tools? | Pila de D04 | [09 §2](09_skill_guardrails_middleware_xbrl.md); duda 11 |
| P12 | ¿Qué había que añadir "en la primera celda y en `miax_s1.py`" para Colab? ¿Los "warrers" son *rerankers*? | Rerank: opcional y después de los tres arreglos | [14 §2, §4](14_clase_pistas_del_profesor.md), [11 §11](11_skill_mejora_retrieval.md); duda 12 |
| P13 | ¿Cuentan como propias las preguntas generadas con ayuda de un LLM y curadas a mano? | Se marcan con el extra `origen` (`manual` o `asistida_curada`) para poder separarlas | [10 §9](10_skill_golden_set.md), [17 §3.8](17_repo_generative_ai.md) |
| P14 | ¿Hay formato o extensión de referencia para el PDF? Las ciegas se ejecutan el 24 y el PDF se entrega el 23: ¿se puede añadir después un anexo con ellas? | Propuesta propia: PDF apaisado de 9 páginas más anexos; las ciegas, en pantalla el 24 | [13 §9](13_skill_medicion_informe_presentacion.md) |
| P15 | ¿El repo tiene que ser público o basta con invitar al profesor? | Sin decidir | [13 §10](13_skill_medicion_informe_presentacion.md) |

### Por verificar al implementar

**En la prueba de humo con la API real, antes del 17** ([08 §10](08_skill_agente_salida_estructurada.md),
[09 §9](09_skill_guardrails_middleware_xbrl.md)). Todo lo marcado (probado) usa un modelo falso:
- **Coste:** si `model_name` casa con las claves de `precios.json` (si no, el callback no cuenta nada y `coste()` lanza `KeyError`); si
  llegan `cost`, `cache_read` y tokens de razonamiento; si OpenRouter aplica caché de prompt a Gemini 3.x, y en qué unidad da la API los
  precios (por token, ×10⁶). Sin `cost`, el coste es la fórmula; sin `cache_read`, una cota superior (D16)
  ([13 §2](13_skill_medicion_informe_presentacion.md), [16 §3.6](16_repo_transformers_labs.md), [17 §3.6](17_repo_generative_ai.md)).
- **Tool calling:** si pide tool calls paralelas en un solo `AIMessage` (si no, la comparativa cuesta una vuelta más) y si OpenRouter y
  Gemini respetan `tool_choice` ([05 §2](05_teoria_agentes_react_tools.md), [08 §11](08_skill_agente_salida_estructurada.md)); si el
  bucle manual necesita reenviar los metadatos de razonamiento de Gemini 3 ([08 §8](08_skill_agente_salida_estructurada.md)).
- **Salida estructurada:** si `structured_response` llega válida con `ToolStrategy`, qué hace con los errores de validación y cuántas
  veces llega `None`, también en `reescribir()` ([11 §7](11_skill_mejora_retrieval.md), [15 §3.4](15_repo_genai_labs.md));
  `ProviderStrategy`, solo si alguien la prueba ([05 §5](05_teoria_agentes_react_tools.md)).
- **Determinismo:** si `temperature=0` repite trayectoria y respuesta y si `seed` sirve; si no, se ejecuta el baseline dos veces y se
  reporta el ruido (D21, [06 §9](06_teoria_evaluacion_llms.md), [13 §4](13_skill_medicion_informe_presentacion.md)).
- **Guardrails:** si obedece el "Tool call limit exceeded" o llega a `ModelCallLimit`, si corrige tras el `[VERIFICADOR XBRL]`, si
  `parse_cifras` da falsos desajustes con su forma real de escribir cifras (prosa en español, importes que no son XBRL) y si responde
  en el mismo mensaje que una tool ([09 §6, §9](09_skill_guardrails_middleware_xbrl.md)).
- **Tokens:** la ventana de contexto real de gemini-3.8-flash por OpenRouter y lo que cuestan de verdad los esquemas de las cuatro
  tools, estimados en 1.700–2.000 tokens por llamada ([03 §1](03_teoria_tokenizacion_embeddings.md), [07 §3](07_skill_herramientas_docstrings.md)).

**Retrieval y embeddings** (hace falta un venv con sentence-transformers y faiss; el del stack no los tiene):
- Si bge-small trunca a 512 tokens los 6 chunks de 513–547 y con qué tokenizer se contó `n_tokens`: un ancla al final de esos chunks
  solo la alcanzaría BM25 ([02 §3](02_datos_corpus_y_xbrl.md), [03 §3](03_teoria_tokenizacion_embeddings.md), [16 §3.7](16_repo_transformers_labs.md)).
- La API de faiss-cpu 1.15 y sentence-transformers 6.0.1, sin introspección: `reconstruct_n` y `write_index`
  ([11 §3, §11](11_skill_mejora_retrieval.md)) y `CrossEncoder` ([04 §6](04_teoria_rag_retrieval.md)). El código de 24 se probó con
  índice y codificador falsos, y el de 26 que carga FAISS y bge solo compila.
- Si bge-small-**en** recupera peor con la pregunta en español: se resuelve midiendo el paso 0 frente al paso 3 de la escalera
  ([03 §3](03_teoria_tokenizacion_embeddings.md), [11 §2](11_skill_mejora_retrieval.md)).

**Golden, jueces y evaluadores:**
- Localizar en el Item 8 de NVDA FY2025 una frase sobre el split 10:1 que sirva de ancla y de cita (gN-013 de
  [10 §7](10_skill_golden_set.md), [08 §9](08_skill_agente_salida_estructurada.md)).
- Validar a los jueces con 30–40 pares etiquetados a mano (~20 para `correcta`) y medir su coste real, estimado en ~0,001 USD por
  llamada ([12 §6, §9](12_skill_evaluadores.md)); calibrar el umbral 0,8 de `casi_literal` con 10–15 citas reales
  ([16 §3.2](16_repo_transformers_labs.md)).

**Clon limpio y entrega** (D25, [13 §10](13_skill_medicion_informe_presentacion.md)):
- ~~Decidir si el corpus va en el repo~~: decidido, `data/` se versiona ([data/README.md](../data/README.md)). Queda fijar las
  versiones de `pandas` y `pyarrow` (la de Colab el día del ensayo; [16](16_repo_transformers_labs.md) se probó con pandas 2.3.3).
- En el ensayo del clon limpio, antes del 22-sep: la primera ejecución baja ~130 MB de bge ([02 §8](02_datos_corpus_y_xbrl.md)),
  instalar versiones fijadas puede obligar a reiniciar el runtime y `getpass` detiene un "Run all" desatendido.
- Revisar los precios el 22-sep (D24) y mirar el saldo antes de la ejecución final: el USD real sale del primer `resumen.json`
  ([13 §4](13_skill_medicion_informe_presentacion.md)).

**Revisar tras las próximas sesiones:** [04](04_teoria_rag_retrieval.md) y [14 §7](14_clase_pistas_del_profesor.md), cuando haya
transcripción de la clase de RAG del 12-sep (hoy solo hay slides) y tras el 17 (se abre `search_filings`);
[05](05_teoria_agentes_react_tools.md), tras el 18 (ReAct) y el 19 (MCP, ADK y A2A); [07](07_skill_herramientas_docstrings.md), tras el 17
(solución del ejercicio 2); [11](11_skill_mejora_retrieval.md), tras el 17 (cómo mide el profesor el filtro);
[12](12_skill_evaluadores.md), tras el 17 (cómo plantea `uso_la_tool_correcta` y `cita_correcta`).

**Qué no se ha podido verificar al escribir los docs:** nada se ha ejecutado contra gemini-3.8-flash (todo lo "probado" usa
`GenericFakeChatModel`, sin red); el venv del stack no tiene faiss, sentence-transformers ni pandas, así que ese código se probó con
dobles o solo compila; la clase de RAG del 12-sep no tiene transcripción, y la sesión del 17, el evaluador del 24 y las ciegas aún no se
conocen. El resto de ⚠️ sueltos está marcado en cada doc, junto a lo que afecta: casi todos son casos de lo anterior, matices teóricos
sin fuente o marcas de API obsoleta en las tablas de 15–17.

## Fuentes

- Cabeceras (`Requisitos`, `Lee antes`, `Fuentes`, versión) e índices de secciones de los docs Markdown de `docs/` (`00`–`18` y este
  índice), leídos el 12-sep-2026 y revisados tras la renumeración consecutiva.
- Firmas de `ToolCallLimitMiddleware` y `ModelCallLimitMiddleware` comprobadas en el venv del stack (venv).
- `.gitignore` del repo (excluye `docs/raw/` y `data/dataset.rar`), `.gitattributes` (`data/` sin conversión de fin de línea) y
  listado de `docs/raw/` y `data/` en disco.
- `docs/raw/_notas/_mapa_cobertura.md` (nota interna, no versionada): §0 (V1–V7), §2 (C01–C32) y §4 (D00–D25), resumidos arriba;
  §3 (huecos), en los pendientes.
- Revisión de cierre del 12-sep, con un script sobre los `.md` de `docs/`: los enlaces relativos apuntan a ficheros y anclas que existen,
  cada `[NN §x]` apunta a una sección que existe, no hay claves ni tokens (`sk-…`, `OPENROUTER_API_KEY=` con valor, `AIza…`, `hf_…`,
  `ghp_…`) ni en los `.md` ni en el `.docx`, y no hay más subcarpetas que `raw/`. Dudas: [01 §6](01_requisitos_y_contratos.md),
  [14 §8](14_clase_pistas_del_profesor.md) y los ⚠️ de cada doc.
- [enunciado · Datos básicos, §1–§5]; [notebook S1 · celda 33] vía [14 §1](14_clase_pistas_del_profesor.md).
